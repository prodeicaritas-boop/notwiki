import os
import json
import re
import yt_dlp
from datetime import datetime

DATA_DIR = 'data'
METADATA_FILE = os.path.join(DATA_DIR, 'metadata.json')
STATE_FILE = os.path.join(DATA_DIR, 'state.json')
SOURCES_FILE = 'sources.txt'

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'

def setup_environment():
    """Ensures data directory exists."""
    os.makedirs(DATA_DIR, exist_ok=True)

def load_json(filepath, default=None):
    if default is None:
        default = []
    if not os.path.exists(filepath):
        return default
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return default

def validate_data(data):
    """Confirms data is a valid list of dictionaries."""
    if not isinstance(data, list):
        print("Error: Data is not a list.")
        return False
    for item in data:
        if not isinstance(item, dict):
            print("Error: Data contains non-dict items.")
            return False
    return True

def atomic_save(filepath, data):
    """Writes data to a temp file, then atomically renames it."""
    tmp_filepath = filepath + '.tmp'
    try:
        with open(tmp_filepath, 'w') as f:
            json.dump(data, f, indent=4)
        os.replace(tmp_filepath, filepath)
    except Exception as e:
        print(f"Error saving JSON to {filepath}: {e}")
        if os.path.exists(tmp_filepath):
            os.remove(tmp_filepath)
        raise e

def extract_url(line):
    """Extracts the first URL starting with http from the line using Regex."""
    match = re.search(r'(http\S+)', line)
    if match:
        url = match.group(1)
        return url.rstrip('>"\'')
    return None

def fetch_items(url, limit=3):
    ydl_opts = {
        'extract_flat': False, # Critical: Resolve direct links
        'format': 'best[ext=mp4]/best', # Ensure compatible video formats
        'playlist_items': f'1-{limit}',
        'quiet': True,
        'ignoreerrors': True,
        'user_agent': USER_AGENT,
    }

    items = []
    # Network Safety: Catch errors inside the loop
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            entries = []
            if 'entries' in info:
                entries = info['entries']
            else:
                entries = [info]

            for entry in entries:
                if entry is None: continue
                items.append(entry)
    except Exception as e:
        print(f"Error fetching items from {url}: {e}")

    return items

def process_item(entry):
    """Extracts relevant fields with strict fallback logic."""
    title = entry.get('title', 'N/A')

    # Metadata Fallbacks: If description is missing, set it equal to the title.
    description = entry.get('description')
    if not description or description == 'N/A':
        description = title

    # Truncate descriptions to 160 characters.
    if len(description) > 160:
        description = description[:160]

    # Extraction Logic: Prefer direct stream link (url), fallback to webpage_url
    direct_url = entry.get('url')
    webpage_url = entry.get('webpage_url', 'N/A')

    final_url = direct_url if direct_url else webpage_url

    # Metadata Fallbacks: If a thumbnail is missing, use 'N/A'
    thumbnail = 'N/A'
    thumbnails = entry.get('thumbnails')
    if thumbnails and isinstance(thumbnails, list) and len(thumbnails) > 0:
        thumbnail = thumbnails[-1].get('url', 'N/A')
    elif entry.get('thumbnail'):
        thumbnail = entry.get('thumbnail')

    # Stable Date Stamping: Use the current system date.
    scrape_date = datetime.now().strftime('%B %d, %Y')

    return {
        'title': title,
        'description': description,
        'url': final_url,
        'thumbnail': thumbnail,
        'scrape_date': scrape_date,
        'id': entry.get('id')
    }

def main():
    setup_environment()

    # 1. Load Sources
    if not os.path.exists(SOURCES_FILE):
        print("Error: sources.txt not found.")
        return

    with open(SOURCES_FILE, 'r') as f:
        lines = f.readlines()

    if not lines:
        print("Error: sources.txt is empty.")
        return

    # Extract valid URLs
    source_urls = []
    for line in lines:
        url = extract_url(line)
        if url:
            source_urls.append(url)

    if not source_urls:
        print("No valid sources found in sources.txt.")
        return

    # 2. Load State & Metadata
    state = load_json(STATE_FILE, default={})
    metadata = load_json(METADATA_FILE, default=[])

    # Deduplication Set (Based on ID)
    seen_ids = set(item.get('id') for item in metadata if item.get('id'))

    items_to_add = []
    new_items_count = 0

    # 3. Process Each Source
    for source_url in source_urls:
        print(f"Processing source: {source_url}")

        # Fetch top 3
        raw_items = fetch_items(source_url, limit=3)

        if not raw_items:
            continue

        # Update State (Latest ID)
        # We assume the first item is the latest
        latest_item = raw_items[0]
        latest_id = latest_item.get('id')

        if latest_id:
            state[source_url] = latest_id

        for entry in raw_items:
            try:
                processed_item = process_item(entry)

                # Deduplication Check (ID based)
                item_id = processed_item['id']
                if item_id in seen_ids:
                    continue

                # Add valid item
                items_to_add.append(processed_item)
                seen_ids.add(item_id)
                new_items_count += 1

            except Exception as e:
                print(f"Error processing item from {source_url}: {e}")
                continue

    # 4. Save Valid Items
    if items_to_add:
        # Prepend new items
        final_metadata = items_to_add + metadata
        # Limit to 100
        final_metadata = final_metadata[:100]

        # Validation
        if validate_data(final_metadata):
            atomic_save(METADATA_FILE, final_metadata)
            atomic_save(STATE_FILE, state) # Save state if we saved metadata
            print(f"Success: {new_items_count} new items added. Total database size: {len(final_metadata)}.")
        else:
            print("Validation failed. Aborting save.")
    else:
        # Save state anyway if changed?
        atomic_save(STATE_FILE, state)
        print("No new items found.")

if __name__ == "__main__":
    main()
