import os
import json
import time
import logging
import hashlib
import argparse
import random
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import urllib3
import glob

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
    Uses random User-Agents per request via headers override.
    Returns (url, status_code/error, is_critical_failure)
    """
    # Use random User-Agent for this specific check
    headers = {"User-Agent": random.choice(config.USER_AGENTS)}

    try:
        # timeout=3 as requested
        response = session.head(url, headers=headers, allow_redirects=True, timeout=3, verify=False)

        # Determine if this is a "critical" failure type for the circuit breaker (403/404/429)
        is_critical = response.status_code in [403, 404, 429]

        if response.status_code >= 400:
            # Retry with GET just in case HEAD is blocked (405 Method Not Allowed, 403 Forbidden)
            if response.status_code in [405, 403]:
                response = session.get(url, headers=headers, allow_redirects=True, timeout=3, verify=False)
                # Re-evaluate critical status after retry
                is_critical = response.status_code in [403, 404, 429]
                if response.status_code < 400:
                    return None

            return (url, response.status_code, is_critical)

    except requests.RequestException as e:
        # Network errors count towards critical failures?
        # Usually connection refused/timeout might be temporary, but if persistent, yes.
        # But instructions say "Failed requests (403/404/429)".
        # So generic connection errors might not trigger the specific breaker logic unless they are HTTP responses.
        # However, a timeout/connection error is not a 403/404/429. It's an exception.
        # I'll stick to status codes for the strict definition, but treat exceptions as broken links.
        return (url, str(e), False)

    return None

def run_scraper_mode(scraper):
    """
    Runs the scraping, parsing, and image processing pipeline.
    """
    logger.info("Running in SCRAPE mode.")

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

def load_latest_links():
    """Retrieves unique URLs from the most recent daily JSON file."""
    files = sorted(glob.glob(os.path.join(config.DAILY_DATA_DIR, "*.json")))
    if not files:
        logger.error("No data files found for Audit Mode.")
        return []

    latest_file = files[-1]
    logger.info(f"Loading links from {latest_file}...")

    try:
        with open(latest_file, 'r') as f:
            data = json.load(f)

        unique_links = set()
        for cat, items in data.items():
            for item in items:
                if 'url' in item:
                    unique_links.add(item['url'])
        return list(unique_links)

    except (IOError, json.JSONDecodeError) as e:
        logger.error(f"Failed to load links from {latest_file}: {e}")
        return []

def run_audit_mode(session):
    """
    Runs only the broken link checker with Circuit Breaker logic.
    """
    logger.info("Running in AUDIT mode.")
    links = load_latest_links()
    if not links:
        logger.warning("No links to check. Exiting Audit Mode.")
        return

    logger.info(f"Starting Circuit Breaker Link Checker for {len(links)} unique links...")

    broken_count = 0
    consecutive_errors = 0
    CIRCUIT_BREAKER_LIMIT = 50

    # Clear previous log
    if os.path.exists(config.BROKEN_LINKS_LOG):
        os.remove(config.BROKEN_LINKS_LOG)

    try:
        with open(config.BROKEN_LINKS_LOG, "w") as f:
            # Max workers = 3 as requested
            with ThreadPoolExecutor(max_workers=3) as executor:
                future_to_url = {executor.submit(check_link, url, session): url for url in links}

                # Iterate as they complete
                for future in as_completed(future_to_url):
                    # Check Circuit Breaker
                    if consecutive_errors > CIRCUIT_BREAKER_LIMIT:
                        msg = f"CRITICAL_STOP: Consecutive error limit ({CIRCUIT_BREAKER_LIMIT}) exceeded at {datetime.now()}. Emergency Stop."
                        logger.critical(msg)
                        f.write(msg + "\n")
                        print(msg)

                        # Cancel remaining futures
                        executor.shutdown(wait=False, cancel_futures=True)
                        return

                    result = future.result()
                    if result:
                        url, error, is_critical = result
                        log_msg = f"BROKEN: {url} | Error: {error}"
                        print(log_msg)
                        f.write(log_msg + "\n")
                        broken_count += 1

                        if is_critical:
                            consecutive_errors += 1
                        else:
                            # Reset if it's a broken link but not a "critical" http error?
                            # Prompt: "If the consecutive error count exceeds 50".
                            # Usually means 50 errors in a row.
                            # If we get a 404, that's an error.
                            # If we get a 200 (None result), we reset.
                            # So:
                            consecutive_errors += 1
                    else:
                        # Success (None result)
                        consecutive_errors = 0

    except IOError as e:
        logger.error(f"Failed to write to broken links log: {e}")

    logger.info(f"Audit finished. Found {broken_count} broken links.")

def main():
    parser = argparse.ArgumentParser(description="FMHY Scraper Ecosystem")
    parser.add_argument("--mode", choices=["scrape", "audit"], default="scrape", help="Operation mode")
    args = parser.parse_args()

    start_time = time.time()

    # Ensure directories exist
    os.makedirs(config.DAILY_DATA_DIR, exist_ok=True)
    os.makedirs(config.THUMBNAILS_DIR, exist_ok=True)
    os.makedirs(config.LOGS_DIR, exist_ok=True)

    scraper = FMHYScraper()

    if args.mode == "scrape":
        run_scraper_mode(scraper)
    elif args.mode == "audit":
        run_audit_mode(scraper.session)

    elapsed = time.time() - start_time
    logger.info(f"Run completed in {elapsed:.2f} seconds.")

if __name__ == "__main__":
    main()
