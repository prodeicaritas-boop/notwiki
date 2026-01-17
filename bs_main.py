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
    Only saves if data is a valid list of dictionaries.
    """
    if not isinstance(data, list):
        print("Error: Data is not a list. Skipping save.")
        return

    if not all(isinstance(item, dict) for item in data):
        print("Error: Data contains non-dictionary items. Skipping save.")
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
    # Environment Safety
    os.makedirs('data', exist_ok=True)

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
                # Use safe_get_text for title
                # HN titles are in .titleline > a (new) or .title > a (old)
                # We prioritize the new selector
                title = safe_get_text(item, '.titleline a', default=None)
                if not title:
                     title = safe_get_text(item, '.title a', default='Untitled')

                # Manual extraction for href since we need the attribute
                link_tag = item.select_one('.titleline a') or item.select_one('.title a')
                if not link_tag or not link_tag.get('href'):
                    continue

                href = link_tag.get('href')
                abs_url = urljoin(url, href)

                if abs_url in seen_urls:
                    continue

                # Description & Truncation
                # Fallback to title as per instructions for HN structure
                description = title
                if len(description) > 160:
                    description = description[:160]

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
