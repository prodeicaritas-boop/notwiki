import os
import json
import re
from datetime import datetime
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

METADATA_FILE = 'data/metadata.json'
SOURCES_FILE = 'sources.txt'

def safe_get_text(element, selector, default='N/A'):
    """
    Safely extracts text from a soup element using a selector.
    Returns default if not found.
    """
    if not element:
        return default
    found = element.select_one(selector)
    return found.get_text(strip=True) if found else default

def atomic_save(data, filepath):
    """
    Saves data to a temporary file and then atomically moves it to the target filepath.
    Only saves if data is a valid list.
    """
    if not isinstance(data, list):
        print("Error: Data is not a valid list. Skipping save.")
        return

    temp_filepath = filepath + '.tmp'
    try:
        with open(temp_filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_filepath, filepath)
        print(f"Successfully saved {len(data)} items to {filepath}")
    except OSError as e:
        print(f"Failed to save data atomically: {e}")
        if os.path.exists(temp_filepath):
            os.remove(temp_filepath)

def main():
    # Initialize/Load Metadata
    if os.path.exists(METADATA_FILE):
        try:
            with open(METADATA_FILE, 'r', encoding='utf-8') as f:
                current_data = json.load(f)
                if not isinstance(current_data, list):
                    current_data = []
        except (json.JSONDecodeError, OSError):
            current_data = []
    else:
        current_data = []

    # Create seen_urls set for deduplication
    seen_urls = {item.get('url') for item in current_data if item.get('url')}

    new_items = []

    # Read Sources
    if not os.path.exists(SOURCES_FILE):
        print(f"{SOURCES_FILE} not found.")
        return

    with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
        sources = f.readlines()

    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    })

    for line in sources:
        # Regex to find URL
        match = re.search(r'(http\S+)', line)
        if not match:
            continue

        url = match.group(1).rstrip('>"\'')
        print(f"Fetching {url}...")

        try:
            response = session.get(url, timeout=15)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'lxml')

            # Target containers = tr.athing
            items = soup.select('tr.athing')

            for item in items:
                # Extract Title & URL
                # HN structure: <span class="titleline"><a href="...">Title</a>...</span>
                # We need to be careful with selectors.
                # safe_get_text can get title text.
                # But we need the <a> tag for href.

                # Finding the link anchor
                # Try generic selectors often found in tr.athing or specifically for HN
                # The user said "safe_get_text... found = element.select_one(selector)"

                # In tr.athing (HN), the title is in 'span.titleline > a' or just '.title > a' (old HN).
                # Let's try '.titleline a' (modern HN) or fallback to finding the first anchor.

                link_tag = item.select_one('.titleline a')
                if not link_tag:
                     # Fallback for older HN markup or if structure differs
                     link_tag = item.select_one('.title a')

                if not link_tag:
                    continue

                title = link_tag.get_text(strip=True)
                href = link_tag.get('href')

                if not href or not title:
                    continue

                abs_url = urljoin(url, href)

                if abs_url in seen_urls:
                    continue

                # Description & Thumbnail
                # HN doesn't have these in tr.athing.
                # Per instructions: description fallback to title, thumbnail fallback to 'N/A'.
                # Unique Metadata logic from previous prompt: "If description matches title exactly, save as empty string"?
                # The latest prompt said: "Initial Setup: ... Target containers = tr.athing."
                # It didn't explicitly repeat the "empty string if match" rule, but it's a good practice and was requested previously.
                # However, the latest prompt says "Generate ... using this corrected logic" and lists specific points.
                # Point 4 says "Safe Extraction Helper".
                # It doesn't mention the empty string optimization.
                # But it says "description (fallback to title)".
                # I will stick to "fallback to title" as per the new simplified instructions.
                # Wait, strictly: "description: Meta description or first paragraph (truncate to 160 chars; fallback to title)" was in the OLD plan.
                # New simplified blueprint doesn't specify *how* to extract description, just "Target containers = tr.athing".
                # If I target `tr.athing`, I can't get meta description of the page (that's per item).
                # So description IS title.

                description = title
                thumbnail = 'N/A'
                upload_date = datetime.now().strftime('%B %d, %Y')

                item_data = {
                    "title": title,
                    "url": abs_url,
                    "description": description,
                    "thumbnail": thumbnail,
                    "upload_date": upload_date
                }

                new_items.append(item_data)
                seen_urls.add(abs_url)

        except Exception as e:
            # Fault-tolerant loop: Log error and continue
            print(f"Error processing {url}: {e}")
            continue

    # Post-Processing
    if new_items:
        # Prepend new items
        final_data = new_items + current_data
        # Limit to 100
        final_data = final_data[:100]
        # Save
        atomic_save(final_data, METADATA_FILE)
    else:
        print("No new items found.")

if __name__ == '__main__':
    main()
