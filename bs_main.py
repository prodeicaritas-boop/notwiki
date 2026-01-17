import os
import json
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

METADATA_FILE = 'data/metadata.json'
SOURCES_FILE = 'sources.txt'

def safe_get_text(element, selector_list, default='N/A'):
    if not element:
        return default
    if selector_list is None:
        return element.get_text(strip=True) or default

    if isinstance(selector_list, str):
        selector_list = [selector_list]

    for selector in selector_list:
        found = element.select_one(selector)
        if found:
            text = found.get_text(strip=True)
            if text:
                return text
    return default

def atomic_save(data, filepath):
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

def parse_hn(soup, base_url, seen_urls):
    """
    The HackerNews_Ritual: Corrected for Unified Schema.
    Merges metadata into 'description' to match the universal format.
    """
    new_items = []
    # Identify the Head (tr.athing)
    heads = soup.select('tr.athing')

    consecutive_dupes = 0

    for head in heads:
        # The Ritual of the Dual Rows
        body = head.find_next_sibling('tr')
        if not body:
            continue

        # Extract from Head
        link_tag = head.select_one('.titleline a') or head.select_one('.title a')
        if not link_tag:
            continue

        href = link_tag.get('href')
        if not href:
            continue

        abs_url = urljoin(base_url, href)

        # Deduplication Check
        if abs_url in seen_urls:
            consecutive_dupes += 1
            if consecutive_dupes >= 5:
                print(f"Hit 5 consecutive duplicates for {base_url}. Breaking.")
                break
            continue
        else:
            consecutive_dupes = 0

        title = link_tag.get_text(strip=True) or 'Untitled'

        # Extract Metadata Components
        score = safe_get_text(body, '.score', default='')
        user = safe_get_text(body, '.hnuser', default='')
        age = safe_get_text(body, '.age', default='')

        # Comment Count
        comments = ''
        subtext_links = body.select('.subtext a')
        for link in subtext_links:
            text = link.get_text(strip=True)
            if 'comment' in text or 'discuss' in text:
                comments = text
                break

        # FUSE THE DATA (The Correction)
        # Create a single string: "100 points | by user | 2 hours ago | 50 comments"
        meta_parts = []
        if score: meta_parts.append(score)
        if user:
            # Check if 'by ' is already in the text (safe_get_text returns raw text)
            # HN raw text usually is just username, "by" is separate in HTML often, but sometimes inside.
            # Let's check. On HN, <span class="hnuser">username</span>. "by" is outside.
            # So we should add "by ".
            user = f"by {user}"
            meta_parts.append(user)
        if age: meta_parts.append(age)
        if comments: meta_parts.append(comments)

        description = " | ".join(meta_parts)

        scrape_date = datetime.now().strftime('%Y-%m-%d')

        # The Unified Return Object
        item_data = {
            "title": title,
            "url": abs_url,
            "description": description,  # <--- THE HOLY UNIFICATION
            "thumbnail": None,           # HN has no images
            "scrape_date": scrape_date,
            "source": "Hacker News"
        }

        new_items.append(item_data)
        seen_urls.add(abs_url)

    return new_items

def parse_generic(soup, base_url, seen_urls):
    """
    Standard Universal Harvester logic for non-specific domains.
    """
    new_items = []

    # Generic Container Heuristic
    containers = []
    selectors = ['article', 'div.post', 'div.entry', 'li']
    for selector in selectors:
        found = soup.select(selector)
        if found:
            containers = found
            break

    if not containers:
        return []

    consecutive_dupes = 0

    for item in containers:
        # URL Extraction
        link_tag = item.select_one('a[href]')
        if not link_tag:
            continue
        href = link_tag.get('href')
        if not href:
            continue
        abs_url = urljoin(base_url, href)

        # Deduplication
        if abs_url in seen_urls:
            consecutive_dupes += 1
            if consecutive_dupes >= 5:
                print(f"Hit 5 consecutive duplicates for {base_url}. Breaking.")
                break
            continue
        else:
            consecutive_dupes = 0

        # Title
        title = safe_get_text(item, ['h1', 'h2', 'h3', '.title', 'a'])

        # Thumbnail
        thumbnail = 'N/A'
        img_tags = item.select('img')
        target_src = None
        for img in img_tags:
            target_src = img.get('data-src') or img.get('srcset') or img.get('src')
            if target_src:
                    if img.get('srcset'):
                        target_src = target_src.split(',')[0].strip().split(' ')[0]
                    break
        if target_src:
            thumbnail = urljoin(base_url, target_src)

        # Description
        description = safe_get_text(item, ['p', '.summary', '.description'])
        if not description or description == title:
            description = ""
        if len(description) > 160:
            description = description[:160]

        scrape_date = datetime.now().strftime('%Y-%m-%d')

        item_data = {
            "title": title,
            "url": abs_url,
            "description": description,
            "thumbnail": thumbnail,
            "scrape_date": scrape_date,
            "source": "Generic"
        }
        new_items.append(item_data)
        seen_urls.add(abs_url)

    return new_items

def main():
    os.makedirs('data', exist_ok=True)

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

    seen_urls = {item.get('url') for item in current_data if item.get('url')}

    if not os.path.exists(SOURCES_FILE):
        print(f"Warning: {SOURCES_FILE} not found. Exiting.")
        return

    with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    valid_sources = []
    for line in lines:
        match = re.search(r'(http\S+)', line)
        if match:
            valid_sources.append(match.group(1).rstrip('>"\''))

    if not valid_sources:
        print("Warning: No valid sources found in sources.txt. Exiting.")
        return

    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    })

    collected_items = []

    for url in valid_sources:
        print(f"Fetching {url}...")
        try:
            response = session.get(url, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'lxml')

            domain = urlparse(url).netloc

            # Commandment I: The Domain Router
            if 'news.ycombinator.com' in domain:
                items = parse_hn(soup, url, seen_urls)
            else:
                items = parse_generic(soup, url, seen_urls)

            if items:
                print(f"Found {len(items)} new items from {url}.")
                collected_items.extend(items)
            else:
                print(f"No new items found from {url}.")

        except requests.RequestException as e:
            print(f"Error fetching {url}: {e}")
            continue

    if collected_items:
        # Commandment IV: Expansion of Memory (No Limit)
        # Prepend new items to the existing data
        final_data = collected_items + current_data
        atomic_save(final_data, METADATA_FILE)
    else:
        print("No new items found.")

if __name__ == '__main__':
    main()
