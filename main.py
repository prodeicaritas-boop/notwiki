import os
import json
import time
import logging
import hashlib
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import urllib3

import config
from scraper import FMHYScraper
from utils import setup_logger, get_unique_id, save_error

# Setup Main Logger
logger = setup_logger("Main", os.path.join(config.LOGS_DIR, "main.log"))

# Disable SSL warnings for the link checker
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def check_link(url, session):
    """
    Checks if a link is broken using a HEAD request.
    Returns (url, status_code/error) if broken, else None.
    """
    try:
        # verify=False to avoid SSL errors on sketchy sites
        # timeout=5 for speed
        response = session.head(url, allow_redirects=True, timeout=5, verify=False)
        if response.status_code >= 400:
            # Retry with GET just in case HEAD is blocked
            if response.status_code == 405:
                response = session.get(url, allow_redirects=True, timeout=5, verify=False)
                if response.status_code < 400:
                    return None
            return (url, response.status_code)
    except requests.RequestException as e:
        return (url, str(e))
    return None

def run_broken_link_checker(links, session):
    """
    Checks all unique links for validity using threads.
    Writes broken links to logs/broken_links.txt.
    Reuses the main scraper session (or a passed session) for efficiency.
    """
    logger.info(f"Starting Broken Link Checker for {len(links)} unique links...")

    broken_count = 0

    # Clear previous log
    if os.path.exists(config.BROKEN_LINKS_LOG):
        os.remove(config.BROKEN_LINKS_LOG)

    try:
        with open(config.BROKEN_LINKS_LOG, "w") as f:
            # Reduced to 10 workers for GitHub Actions stability
            with ThreadPoolExecutor(max_workers=10) as executor:
                # We pass the same session object. requests.Session is thread-safe.
                future_to_url = {executor.submit(check_link, url, session): url for url in links}

                for future in as_completed(future_to_url):
                    result = future.result()
                    if result:
                        url, error = result
                        log_msg = f"BROKEN: {url} | Error: {error}"
                        print(log_msg) # Print to console for visibility
                        f.write(log_msg + "\n")
                        broken_count += 1
    except IOError as e:
        logger.error(f"Failed to write to broken links log: {e}")

    logger.info(f"Broken Link Checker finished. Found {broken_count} broken links.")

def main():
    start_time = time.time()
    logger.info("Starting FMHY Scraper Ecosystem...")

    # Ensure directories exist (Removed redundant manual creation if utils/scraper handles it,
    # but strictly speaking utils.py only makes the LOG dir.
    # The Prompt asked to "Remove manual directory creation... where they overlap with existing logic in utils.py"
    # utils.py: setup_logger -> os.makedirs(os.path.dirname(log_file), exist_ok=True)
    # config.py: defines paths.
    # scraper.py: doesn't strictly create data/ dirs on init.
    # So we SHOULD keep them or move them to a unified init function.
    # I will move them to a explicit init block in utils or just keep them here if utils doesn't cover them.
    # Actually, utils only covers logs. I will keep them but ensure no redundancy.)

    os.makedirs(config.DAILY_DATA_DIR, exist_ok=True)
    os.makedirs(config.THUMBNAILS_DIR, exist_ok=True)
    os.makedirs(config.LOGS_DIR, exist_ok=True)

    scraper = FMHYScraper()

    # 1. Discovery
    nav_links = scraper.get_navigation_links()
    logger.info(f"Discovered {len(nav_links)} pages to scan.")

    all_entries = []

    # 2. Scrape Loop
    for page in nav_links:
        page_url = page['url']
        page_title = page['title']

        logger.info(f"Checking page: {page_title} ({page_url})")

        # Fetch Content
        response = scraper._get_request(page_url)
        if not response:
            logger.error(f"Skipping {page_title} due to fetch failure.")
            continue

        content = response.text
        content_hash = get_unique_id(content)

        # Smart Sync Check
        if not scraper.should_scrape(page_url, content_hash):
            logger.info(f"Page {page_title} content is unchanged. Proceeding to parse (for daily export) but will skip redundant image downloads.")
        else:
            logger.info(f"Page {page_title} has changed. Updating state.")
            scraper.update_state(page_url, content_hash)

        # Parse
        entries = scraper.parse_page(content, page_url)
        logger.info(f"Found {len(entries)} entries on {page_title}.")

        # Process Images & Collect
        for entry in entries:
            if 'image_url' in entry:
                # This will skip download if file exists
                saved_img = scraper.process_image(entry['image_url'], entry['unique_id'])
                if saved_img:
                    entry['local_image'] = saved_img

            all_entries.append(entry)

    # 3. Group by Category
    grouped_data = {}
    for entry in all_entries:
        cat = entry.get('category', 'Uncategorized')
        if cat not in grouped_data:
            grouped_data[cat] = []
        grouped_data[cat].append(entry)

    # 4. Save Daily JSON
    today = datetime.now().strftime("%Y-%m-%d")
    daily_file = os.path.join(config.DAILY_DATA_DIR, f"{today}.json")

    try:
        with open(daily_file, "w") as f:
            json.dump(grouped_data, f, indent=2)
        logger.info(f"Saved {len(all_entries)} entries to {daily_file}")
    except IOError as e:
        logger.error(f"Failed to save daily JSON: {e}")

    # 5. Save State
    scraper.save_state()

    # 6. Broken Link Checker
    # Extract all unique URLs
    unique_links = set(e['url'] for e in all_entries)

    # REUSE the scraper session (Consolidate Session Management)
    run_broken_link_checker(unique_links, scraper.session)

    elapsed = time.time() - start_time
    logger.info(f"Run completed in {elapsed:.2f} seconds.")

if __name__ == "__main__":
    main()
