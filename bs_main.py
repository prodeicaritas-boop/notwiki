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
    If selector is None, extracts text from the element itself.
    Returns default if not found.
    """
    if not element:
        return default
    if selector:
        found = element.select_one(selector)
    else:
        found = element
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
    # 1. Environment Check
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

    # High-Efficiency Delta Loop: Set for O(1) lookups
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
        # Regex extraction
        match = re.search(r'(http\S+)', line)
        if not match:
            continue

        url = match.group(1).rstrip('>"\'')
        print(f"Fetching {url}...")

        try:
            response = session.get(url, timeout=15)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'lxml')

            # 2. Global Metadata Discovery
            global_thumbnail = 'N/A'
            og_image = soup.select_one('meta[property="og:image"]') or \
                       soup.select_one('meta[name="twitter:image"]')
            if og_image and og_image.get('content'):
                global_thumbnail = urljoin(url, og_image.get('content'))

            # 4. Universal Extraction & Fallbacks
            container_selectors = ['tr.athing', 'article', 'div.post', '.item', 'li']
            items = []
            for selector in container_selectors:
                items = soup.select(selector)
                if items:
                    break

            if not items:
                print(f"No items found for {url} with generic selectors.")
                continue

            # Reset consecutive duplicates counter for EACH source
            consecutive_dupes = 0

            for item in items:
                # Find Link & Title - Robust Hierarchy
                link_tag = item.select_one('.titleline a') or \
                           item.select_one('.title a') or \
                           item.select_one('h1 a') or \
                           item.select_one('h2 a')

                if not link_tag:
                    # Fallback: Find largest text-bearing anchor
                    anchors = item.find_all('a', href=True)
                    if anchors:
                        # Sort by text length descending
                        anchors.sort(key=lambda a: len(a.get_text(strip=True)), reverse=True)
                        link_tag = anchors[0]

                if not link_tag or not link_tag.get('href'):
                    continue

                href = link_tag.get('href')
                abs_url = urljoin(url, href)

                # 3. High-Efficiency Delta Logic (Stop-Gate)
                if abs_url in seen_urls:
                    consecutive_dupes += 1
                    if consecutive_dupes >= 5:
                        print(f"Hit 5 consecutive duplicates for {url}. Breaking.")
                        break
                    continue
                else:
                    consecutive_dupes = 0

                # Title - Use Universal Helper
                title = safe_get_text(link_tag, None, default='Untitled')

                # Thumbnail Extraction - Improved Logic
                thumbnail = 'N/A'

                # 1. Check specific attributes on img tags
                candidates = item.select('img[data-src], img[srcset], img[class*="thumb"]')

                target_img_src = None
                if candidates:
                    img = candidates[0]
                    target_img_src = img.get('src') or img.get('data-src')
                    if not target_img_src and img.get('srcset'):
                        target_img_src = img.get('srcset').split(',')[0].strip().split(' ')[0]

                # 2. Fallback to any img
                if not target_img_src:
                     img_tag = item.select_one('img')
                     if img_tag:
                         target_img_src = img_tag.get('src')

                if target_img_src:
                    thumbnail = urljoin(url, target_img_src)
                else:
                    # 3. Fallback to Global
                    thumbnail = global_thumbnail

                # Description Extraction
                description = safe_get_text(item, 'p', default='')
                if not description:
                     description = safe_get_text(item, '.description', default='')

                # Space-Saving Logic
                if description == title or not description:
                    description = ""

                # Truncate
                if len(description) > 160:
                    description = description[:160]

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
            # 6. Network Safety
            print(f"Error processing {url}: {e}")
            continue

    # Post-Processing
    if new_items:
        # Prepend new items
        final_data = new_items + current_data
        # Limit to 100
        final_data = final_data[:100]
        # Atomic Save
        atomic_save(final_data, METADATA_FILE)
    else:
        print("No new items found.")

if __name__ == '__main__':
    main()
