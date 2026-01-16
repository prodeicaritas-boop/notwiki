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
    # Regex Only: Do not use simple string stripping. Use re.search(r'(http\S+)', line)
    match = re.search(r'(http\S+)', line)
    if match:
        url = match.group(1)
        # We might still want to strip trailing punctuation that regex might catch if not careful,
        # but the prompt specifically says "explicitly ignoring any <> tags".
        # <http://example.com> -> group 1 is http://example.com>
        # The prompt says "Use re.search(r'(http\S+)', line) to extract only the URL"
        # If the input is <http://...>, \S includes >.
        # So we probably still need to clean the trailing > if the regex captures it.
        # But the prompt implies the regex *is* the solution.
        # Let's clean standard delimiters just in case, to be safe "Production Level".
        return url.rstrip('>"\'')
    return None

def fetch_items(url, limit=3):
    ydl_opts = {
        'extract_flat': True,
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

    webpage_url = entry.get('webpage_url', entry.get('url', 'N/A'))

    # Metadata Fallbacks: If a thumbnail is missing, use 'N/A'
    thumbnail = 'N/A'
    thumbnails = entry.get('thumbnails')
    if thumbnails and isinstance(thumbnails, list) and len(thumbnails) > 0:
        thumbnail = thumbnails[-1].get('url', 'N/A')
    elif entry.get('thumbnail'):
        thumbnail = entry.get('thumbnail')

    # Stable Date Stamping: Use the current system date.
    upload_date = datetime.now().strftime('%B %d, %Y')

    # Metadata only check: if url or thumbnail is missing/NA
    is_metadata_only = False
    if thumbnail == 'N/A' or webpage_url == 'N/A':
        is_metadata_only = True

    return {
        'title': title,
        'description': description,
        'url': webpage_url,
        'thumbnail': thumbnail,
        'upload_date': upload_date,
        'id': entry.get('id')
    }, is_metadata_only

def main():
    setup_environment()

    # 1. Read sources
    if not os.path.exists(SOURCES_FILE):
        print("No sources found")
        sys.exit(1)

    with open(SOURCES_FILE, 'r') as f:
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

    # 2. Load State
    state = load_json(STATE_FILE, default={})
    last_id = state.get(source_url)

    legacy_id = load_legacy_state(source_url)
    if legacy_id and not last_id:
        last_id = legacy_id

    # 3. Fetch Items & Delta Check
    raw_items = fetch_items(source_url, limit=3)

    if not raw_items:
        print("No items found.")
        sys.exit(0)

    latest_item = raw_items[0]
    current_latest_id = latest_item.get('id')

    # Delta Check
    if current_latest_id == last_id and last_id is not None:
        print('Database is up to date')
        # If we successfully checked against legacy ID, save state now and archive legacy
        if legacy_id and source_url not in state:
             state[source_url] = legacy_id
             try:
                 atomic_save(STATE_FILE, state)
                 archive_legacy_state()
             except Exception:
                 pass
        sys.exit(0)

    # 4. Processing & Deduplication
    new_items_count = 0
    metadata_only_count = 0

    # Load existing metadata
    metadata = load_json(METADATA_FILE, default=[])

    # High-Efficiency Deduplication: Set of URLs
    existing_urls = set(item.get('url') for item in metadata if item.get('url'))

    items_to_add = []

    for entry in raw_items:
        try:
            processed_item, is_meta_only = process_item(entry)
            item_url = processed_item['url']

            # Check every new item against this set
            if item_url in existing_urls:
                continue

            # Add item and update set immediately
            items_to_add.append(processed_item)
            existing_urls.add(item_url)

            if is_meta_only:
                metadata_only_count += 1
            new_items_count += 1

        except Exception as e:
            print(f"Error processing item: {e}")
            continue

    # 5. Database Merge
    # Add new items to the top
    final_metadata = items_to_add + metadata

    # Keep only top 100
    final_metadata = final_metadata[:100]

    # Validation Gate
    if not validate_data(final_metadata):
        print("Error: Validation failed on final data. Aborting save.")
        sys.exit(1)

    # Update State
    if current_latest_id:
        state[source_url] = current_latest_id

    # 6. Atomic Save & Finalization
    try:
        atomic_save(METADATA_FILE, final_metadata)
        atomic_save(STATE_FILE, state)

        # State Migration: Only archive at the very end if successful
        if legacy_id:
             archive_legacy_state()

    except Exception as e:
        print(f"Error saving data: {e}")
        sys.exit(1)

    # 7. Output
    print(f"Success: {new_items_count} new items added. Metadata-only: {metadata_only_count}. Total database size: {len(final_metadata)}.")

if __name__ == "__main__":
    main()
