import os
import sys
import json
import shutil
import yt_dlp
from datetime import datetime

DATA_DIR = 'data'
METADATA_FILE = os.path.join(DATA_DIR, 'metadata.json')
STATE_FILE = os.path.join(DATA_DIR, 'state.json')
OLD_STATE_FILE = os.path.join(DATA_DIR, 'state.txt')
SOURCES_FILE = 'sources.txt'

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'

def setup_environment():
    """Ensures data directory exists."""
    os.makedirs(DATA_DIR, exist_ok=True)

def migrate_state(source_url):
    """Migrates old state.txt to state.json if it exists."""
    if os.path.exists(OLD_STATE_FILE):
        try:
            with open(OLD_STATE_FILE, 'r') as f:
                content = f.read().strip()

            # Assuming old state file contained just the ID
            initial_state = {}
            if content:
                 initial_state[source_url] = content

            # If state.json exists, we merge, otherwise we create
            current_state = {}
            if os.path.exists(STATE_FILE):
                try:
                    with open(STATE_FILE, 'r') as f:
                        current_state = json.load(f)
                except json.JSONDecodeError:
                    pass

            # Update current state with old state info if not present
            if source_url not in current_state and content:
                current_state[source_url] = content

            with open(STATE_FILE, 'w') as f:
                json.dump(current_state, f, indent=4)

            # Archive old file
            shutil.move(OLD_STATE_FILE, OLD_STATE_FILE + '.bak')
            print(f"Migrated {OLD_STATE_FILE} to {STATE_FILE}")

        except Exception as e:
            print(f"Error migrating state file: {e}")

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

def save_json(filepath, data):
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=4)

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

def get_latest_id(url):
    ydl_opts = {
        'extract_flat': True,
        'playlist_items': '1',
        'quiet': True,
        'ignoreerrors': True,
        'user_agent': USER_AGENT,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if 'entries' in info and info['entries']:
            return info['entries'][0].get('id')
        elif 'id' in info:
            return info['id']
    return None

def fetch_items(url, limit=3):
    ydl_opts = {
        'extract_flat': True, # Performance optimization
        'playlist_items': f'1-{limit}',
        'quiet': True,
        'ignoreerrors': True,
        'user_agent': USER_AGENT,
    }

    items = []
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            entries = []
            if 'entries' in info:
                entries = info['entries']
            else:
                entries = [info]

            for entry in entries:
                if entry is None: continue # ignoreerrors=True can produce Nones
                items.append(entry)
        except Exception as e:
            print(f"Error fetching items: {e}")

    return items

def format_date(date_str):
    """Converts YYYYMMDD to Month Day, Year."""
    if not date_str or date_str == 'N/A':
        return 'N/A'
    try:
        dt = datetime.strptime(date_str, '%Y%m%d')
        return dt.strftime('%B %d, %Y')
    except ValueError:
        return date_str

def process_item(entry):
    """Extracts relevant fields with fallback logic."""
    title = entry.get('title', 'N/A')

    # Truncate description to 160 characters
    description = entry.get('description', 'N/A')
    if description and description != 'N/A' and len(description) > 160:
        description = description[:160]

    webpage_url = entry.get('webpage_url', entry.get('url', 'N/A'))

    # Handle thumbnails - extract_flat might return a list of dicts or nothing
    thumbnail = 'N/A'
    thumbnails = entry.get('thumbnails')
    if thumbnails and isinstance(thumbnails, list) and len(thumbnails) > 0:
        # Try to get the last one (usually highest quality) or just the first
        thumbnail = thumbnails[-1].get('url', 'N/A')
    elif entry.get('thumbnail'):
        thumbnail = entry.get('thumbnail')

    upload_date = entry.get('upload_date', 'N/A')
    formatted_date = format_date(upload_date)

    # Metadata only check: if url or thumbnail is missing/NA
    is_metadata_only = False
    if thumbnail == 'N/A' or webpage_url == 'N/A':
        is_metadata_only = True

    return {
        'title': title,
        'description': description,
        'url': webpage_url,
        'thumbnail': thumbnail,
        'upload_date': formatted_date,
        'id': entry.get('id')
    }, is_metadata_only

def main():
    setup_environment()

    # 1. Read sources
    if not os.path.exists(SOURCES_FILE):
        print("No sources found")
        sys.exit(1)

    with open(SOURCES_FILE, 'r') as f:
        lines = [l.strip() for l in f if l.strip()]

    if not lines:
        print("No sources found")
        sys.exit(1)

    source_url = lines[0] # Single source check

    # 2. Migration
    migrate_state(source_url)

    # 3. Load State
    state = load_json(STATE_FILE, default={})
    last_id = state.get(source_url)

    # 4. Delta Check
    try:
        current_latest_id = get_latest_id(source_url)
    except Exception as e:
        print(f"Error checking source: {e}")
        sys.exit(1)

    if current_latest_id == last_id and last_id is not None:
        print('Database is up to date')
        sys.exit(0)

    # 5. Robust Extraction
    new_items_count = 0
    metadata_only_count = 0

    raw_items = fetch_items(source_url, limit=3)

    # Load existing metadata for deduplication
    metadata = load_json(METADATA_FILE, default=[])
    existing_urls = set(item.get('url') for item in metadata if item.get('url'))

    items_to_add = []

    for entry in raw_items:
        try:
            processed_item, is_meta_only = process_item(entry)

            # Deduplication
            if processed_item['url'] in existing_urls:
                continue

            # Double check against items we are about to add in this run
            if any(i['url'] == processed_item['url'] for i in items_to_add):
                continue

            items_to_add.append(processed_item)
            if is_meta_only:
                metadata_only_count += 1
            new_items_count += 1

        except Exception as e:
            # Error Handling: For each item, use a try...except block.
            print(f"Error processing item: {e}")
            continue

    # 6. Database Logic
    # Add new items to the top
    final_metadata = items_to_add + metadata

    # Keep only top 100
    final_metadata = final_metadata[:100]

    # 8. Validation (Moved before save)
    if not validate_data(final_metadata):
        print("Error: Validation failed. Aborting save.")
        sys.exit(1)

    # Update State
    if current_latest_id:
        state[source_url] = current_latest_id

    # 7. Save
    save_json(METADATA_FILE, final_metadata)
    save_json(STATE_FILE, state)

    # 9. Output
    print(f"Success: {new_items_count} new items added. Metadata-only: {metadata_only_count}. Total database size: {len(final_metadata)}.")

if __name__ == "__main__":
    main()
