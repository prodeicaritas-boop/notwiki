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

    # Extraction Logic: Prefer direct stream link
    webpage_url = entry.get('webpage_url', 'N/A')
    direct_url = entry.get('url')

    final_url = webpage_url
    if direct_url:
        final_url = direct_url

    # Metadata Fallbacks: If a thumbnail is missing, use 'N/A'
    thumbnail = 'N/A'
    thumbnails = entry.get('thumbnails')
    if thumbnails and isinstance(thumbnails, list) and len(thumbnails) > 0:
        thumbnail = thumbnails[-1].get('url', 'N/A')
    elif entry.get('thumbnail'):
        thumbnail = entry.get('thumbnail')

    # Stable Date Stamping: Use the current system date.
    upload_date = datetime.now().strftime('%B %d, %Y')

    return {
        'title': title,
        'description': description,
        'url': final_url,
        'thumbnail': thumbnail,
        'upload_date': upload_date,
        'id': entry.get('id')
    }

def main():
    setup_environment()

    # 1. Load Sources
    if not os.path.exists(SOURCES_FILE):
        print("No sources found")
        return

    with open(SOURCES_FILE, 'r') as f:
        lines = f.readlines()

    # Extract valid URLs
    source_urls = []
    for line in lines:
        url = extract_url(line)
        if url:
            source_urls.append(url)

    if not source_urls:
        print("No valid sources found")
        return

    # 2. Load State & Metadata
    state = load_json(STATE_FILE, default={})
    metadata = load_json(METADATA_FILE, default=[])

    # Deduplication Set
    existing_urls = set(item.get('url') for item in metadata if item.get('url'))
    # Also track IDs to be safe if url changes (e.g. stream link expiry)?
    # Prompt says "Deduplication: Keep the set() logic to check for existing URLs."
    # Since we are now using direct stream links, these might change or be different from webpage_urls.
    # However, "Deduplicate against metadata.json". If metadata.json has old items with webpage_url (from prev version)
    # and now we get stream url, they won't match.
    # Ideally we should deduplicate by ID if available.
    # But strict adherence to "Keep the set() logic to check for existing URLs".
    # I'll stick to URL for now as requested, but maybe add ID check if easy?
    # Let's stick to URL to follow "Keep the set() logic" instruction precisely.
    # Note: Stream URLs (e.g. googlevideo.com/...) expire. Using them for deduplication might be flaky long term.
    # But the prompt asks for "Direct Streaming URL" to be saved.
    # Use case: "Universal Media Harvester".

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

        # Delta Check (Per Source)
        # If latest_id matches state, we might skip processing?
        # The prompt "Final Logic Flow" says: Fetch top 3 -> Extract -> Deduplicate -> Save.
        # It doesn't explicitly say "skip if state matches".
        # But "3. Fault Tolerance... Network Safety...".
        # And "Refactor... to be a production-ready...".
        # Usually we want to skip if up to date to save bandwidth/time, but with "extract_flat: False", fetching metadata is heavy.
        # "Fetch top 3 items" implies we fetch them anyway.
        # So I will process them. The Deduplication logic will handle skipping known items.
        # I will still update the state though.

        if latest_id:
            state[source_url] = latest_id

        for entry in raw_items:
            try:
                processed_item = process_item(entry)

                # Deduplication
                if processed_item['url'] in existing_urls:
                    continue

                # Add valid item
                items_to_add.append(processed_item)
                existing_urls.add(processed_item['url'])
                new_items_count += 1

            except Exception as e:
                print(f"Error processing item from {source_url}: {e}")
                continue

    # 4. Save Valid Items
    if items_to_add:
        # Prepend new items
        final_metadata = items_to_add + metadata
        # Limit? Previous requirement was top 100. New prompt doesn't explicitly mention it,
        # but says "Deduplicate... Save Valid items."
        # I'll keep the top 100 limit to prevent unlimited growth as it was a core requirement before
        # and "production-ready" usually implies bounding resource usage.
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
        # If we just updated state but found no *new* items (all deduped), we should still save state.
        atomic_save(STATE_FILE, state)
        print("No new items found.")

if __name__ == "__main__":
    main()
