import os
import json
import re
from datetime import datetime
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

METADATA_FILE = 'data/metadata.json'
SOURCES_FILE = 'sources.txt'

def safe_get_text(element, selector_list, default='N/A'):
    """
    Safely extracts text from a soup element using a priority list of selectors.
    If selector_list is None, extracts text from the element itself.
    Returns the first match found, stripped of whitespace.
    """
    if not element:
        return default

    if selector_list is None:
        return element.get_text(strip=True) or default

    for selector in selector_list:
        found = element.select_one(selector)
        if found:
            text = found.get_text(strip=True)
            if text:
                return text

    return default

def atomic_save(data, filepath):
    """
    Saves data to a temporary file and then atomically moves it to the target filepath.
    Only saves if data is a valid list of dictionaries.
    """
    if not isinstance(data, list):
        print("Error: Data is not a list. Skipping save.")
        return

    # Strict Validation
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

def find_containers(soup):
    """
    Heuristic to find item containers based on priority.
    """
    # Priority 1: <article> tags or tr.athing (HN specific but widely used in this context)
    containers = soup.select('article')
    if containers:
        return containers

    # Check for tr.athing specifically as per previous instructions context,
    # though strict prompt said "Priority 1: <article>".
    # But "Generic Container Heuristic" implies finding items.
    # HN uses tr.athing.
    containers = soup.select('tr.athing')
    if containers:
        return containers

    # Priority 2: div/section with specific class names
    # We look for common class names
    # CSS selector substring matching
    target_classes = ['post', 'entry', 'article', 'item']
    # Build selector: div[class*="post"], section[class*="post"], ...
    selectors = []
    for tag in ['div', 'section']:
        for cls in target_classes:
            selectors.append(f'{tag}[class*="{cls}"]')

    # Try one by one or all? select allows comma separated.
    combined_selector = ', '.join(selectors)
    containers = soup.select(combined_selector)
    if containers:
        return containers

    # Priority 3: li tags containing h2 or h3
    # This requires filtering
    lis = soup.select('li')
    valid_lis = []
    for li in lis:
        if li.select_one('h2') or li.select_one('h3'):
            valid_lis.append(li)

    if valid_lis:
        return valid_lis

    # Fallback to nothing
    return []

def main():
    # 1. Environment & Setup
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

    # 4. High-Speed Deduplication
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

            # 1. Generic Container Heuristic
            items = find_containers(soup)

            if not items:
                print(f"No containers found for {url}.")
                continue

            consecutive_dupes = 0

            for item in items:
                # 3. Universal Field Extraction

                # URL: First <a> with href
                link_tag = item.select_one('a[href]')
                if not link_tag:
                    continue

                href = link_tag.get('href')
                if not href:
                    continue

                abs_url = urljoin(url, href)

                # 4. Deduplication Logic
                if abs_url in seen_urls:
                    consecutive_dupes += 1
                    if consecutive_dupes >= 5:
                        print(f"Hit 5 consecutive duplicates for {url}. Breaking.")
                        break
                    continue
                else:
                    consecutive_dupes = 0

                # Title
                title = safe_get_text(item, ['h1', 'h2', 'h3', '.title', 'a'])

                # Thumbnail
                thumbnail = 'N/A'
                img_tags = item.select('img')
                # Check attributes
                target_src = None
                for img in img_tags:
                    target_src = img.get('data-src') or img.get('srcset') or img.get('src')
                    if target_src:
                        # If srcset, basic parse
                        if img.get('srcset'):
                             target_src = target_src.split(',')[0].strip().split(' ')[0]
                        break

                if target_src:
                    thumbnail = urljoin(url, target_src)

                # Description
                description = safe_get_text(item, ['p', '.summary', '.description'], default='')

                # Logic: Missing or == Title -> Empty
                if not description or description == title:
                    description = ""

                # Limit
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
