import os
import sys
import json
import shutil
import re
import yt_dlp
from datetime import datetime

DATA_DIR = 'data'
METADATA_FILE = os.path.join(DATA_DIR, 'metadata.json')
STATE_FILE = os.path.join(DATA_DIR, 'state.json')
OLD_STATE_FILE = os.path.join(DATA_DIR, 'state.txt')
SOURCES_FILE = 'sources.txt'

# Standard browser User-Agent
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'

def setup_environment():
    """Ensures data directory exists."""
    os.makedirs(DATA_DIR, exist_ok=True)

def load_legacy_state(source_url):
    """Reads old state.txt and returns the ID if it exists."""
    if os.path.exists(OLD_STATE_FILE):
        try:
            with open(OLD_STATE_FILE, 'r') as f:
                content = f.read().strip()
            if content:
                return content
        except Exception as e:
            print(f"Error reading legacy state file: {e}")
    return None

def archive_legacy_state():
    """Archives the legacy state file."""
    if os.path.exists(OLD_STATE_FILE):
         try:
            shutil.move(OLD_STATE_FILE, OLD_STATE_FILE + '.bak')
            print(f"Archived {OLD_STATE_FILE}")
         except Exception as e:
            print(f"Error archiving legacy state: {e}")

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

def save_json_atomic(filepath, data):
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
    """Extracts the first URL starting with http from the line."""
    match = re.search(r'(http\S+)', line)
    if match:
        # Strip any trailing characters that might be part of tags like > or " or '
        url = match.group(1)
        # Basic cleanup if regex grabbed a trailing >
        url = url.rstrip('>"\'')
        return url
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
                if entry is None: continue
                items.append(entry)
        except Exception as e:
            print(f"Error fetching items: {e}")

    return items

def get_current_date_formatted():
    return datetime.now().strftime('%B %d, %Y')

def format_date(date_str):
    """Converts YYYYMMDD to Month Day, Year. Fallback to current date."""
    if not date_str or date_str == 'N/A':
        return get_current_date_formatted()
    try:
        dt = datetime.strptime(date_str, '%Y%m%d')
        return dt.strftime('%B %d, %Y')
    except ValueError:
        # Malformed date string, fallback to current date as requested
        return get_current_date_formatted()

def process_item(entry):
    """Extracts relevant fields with smart fallback logic."""
    title = entry.get('title', 'N/A')

    # Description Fallback: Use Title if missing
    description = entry.get('description')
    if not description or description == 'N/A':
        description = title

    # Truncate description to 160 characters
    if len(description) > 160:
        description = description[:160]

    webpage_url = entry.get('webpage_url', entry.get('url', 'N/A'))

    # Handle thumbnails
    thumbnail = 'N/A'
    thumbnails = entry.get('thumbnails')
    if thumbnails and isinstance(thumbnails, list) and len(thumbnails) > 0:
        thumbnail = thumbnails[-1].get('url', 'N/A')
    elif entry.get('thumbnail'):
        thumbnail = entry.get('thumbnail')

    # Date Fallback: Use Current Date if missing
    upload_date = entry.get('upload_date')
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
        # Read lines and try to extract valid URL
        lines = f.readlines()

    source_url = None
    for line in lines:
        extracted = extract_url(line)
        if extracted:
            source_url = extracted
            break

    if not source_url:
        print("No valid sources found")
        sys.exit(1)

    # 2. Load State (Memory Only)
    state = load_json(STATE_FILE, default={})
    last_id = state.get(source_url)

    legacy_id = load_legacy_state(source_url)
    # If we have a legacy ID and no current ID for this source, use legacy
    if legacy_id and not last_id:
        last_id = legacy_id

    # 3. Efficiency: Fetch Items & Delta Check combined
    raw_items = fetch_items(source_url, limit=3)

    if not raw_items:
        print("No items found.")
        # Even if no items found, if we loaded legacy state, we should probably migrate it?
        # The prompt says: "If the ID matches state.json, print 'No new content' and exit."
        # It also says: "Migration Integrity: Do not rename state.txt to .bak until the very end of a successful script execution."
        # If we exit here, we technically successfully ran, just found no content.
        # But we haven't 'saved' anything.
        # However, if we just migrated in memory, we might want to save the new state file so next time we don't rely on legacy?
        # Let's be safe: If no items, we can't verify ID, so we just exit.
        sys.exit(0)

    latest_item = raw_items[0]
    current_latest_id = latest_item.get('id')

    if current_latest_id == last_id and last_id is not None:
        print('Database is up to date')
        # If we used legacy_id to match, we should persist this migration
        if legacy_id and source_url not in state:
             state[source_url] = legacy_id
             try:
                 save_json_atomic(STATE_FILE, state)
                 archive_legacy_state()
             except Exception:
                 pass
        sys.exit(0)

    # 5. Robust Extraction & Processing
    new_items_count = 0
    metadata_only_count = 0

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

    # 6. Database Merge
    final_metadata = items_to_add + metadata

    # Keep only top 100
    final_metadata = final_metadata[:100]

    # Validation on Final Metadata before saving (Atomic Safety)
    if not validate_data(final_metadata):
        print("Error: Validation failed on final data. Aborting save.")
        sys.exit(1)

    # Update State
    if current_latest_id:
        state[source_url] = current_latest_id

    # 7. Atomic Save
    try:
        save_json_atomic(METADATA_FILE, final_metadata)
        save_json_atomic(STATE_FILE, state)

        # 8. Migration Integrity
        # Only archive if everything else succeeded
        if legacy_id:
             archive_legacy_state()

    except Exception as e:
        print(f"Error saving data: {e}")
        sys.exit(1)

    # 9. Output
    print(f"Success: {new_items_count} new items added. Metadata-only: {metadata_only_count}. Total database size: {len(final_metadata)}.")

if __name__ == "__main__":
    main()
