import requests
import time
import random
import re
import json
import logging
import os
from io import BytesIO
from PIL import Image, UnidentifiedImageError
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import config
from utils import setup_logger, get_unique_id, save_error

class FMHYScraper:
    def __init__(self):
        self.session = requests.Session()
        self.logger = setup_logger("FMHYScraper", os.path.join(config.LOGS_DIR, "scraper.log"))
        self.base_url = "https://fmhy.net/"
        self.state = self._load_state()

    def _load_state(self):
        """Loads the previous run's state (hashes) from JSON."""
        if os.path.exists(config.STATE_FILE):
            try:
                with open(config.STATE_FILE, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to load state file (JSON error): {e}")
            except IOError as e:
                self.logger.error(f"Failed to load state file (IO error): {e}")
        return {}

    def save_state(self):
        """Saves the current state to JSON."""
        try:
            with open(config.STATE_FILE, 'w') as f:
                json.dump(self.state, f, indent=2)
        except IOError as e:
            self.logger.error(f"Failed to save state file: {e}")

    def should_scrape(self, url, content_hash):
        """
        Checks if the page content has changed since the last run.
        Returns True if it's new or changed.
        """
        # We use the URL as the key in our state dictionary
        last_hash = self.state.get(url)
        if last_hash == content_hash:
            return False
        return True

    def update_state(self, url, content_hash):
        """Updates the known hash for a URL."""
        self.state[url] = content_hash

    def _get_request(self, url):
        """
        Fetches a URL with stealth and reliability mechanisms.
        - Rotates User-Agents.
        - Sleeps randomly (3-7s) before request.
        - Retries on 429 (Too Many Requests) by sleeping 60s.
        """
        max_retries = 3

        for attempt in range(max_retries):
            # 1. Rotate User-Agent
            user_agent = random.choice(config.USER_AGENTS)
            self.session.headers.update({"User-Agent": user_agent})

            # 2. Stealth Sleep (3-7 seconds)
            sleep_time = random.uniform(config.MIN_SLEEP, config.MAX_SLEEP)
            self.logger.info(f"Sleeping for {sleep_time:.2f}s before fetching {url}...")
            time.sleep(sleep_time)

            try:
                response = self.session.get(url, timeout=15)

                # 3. Check for 429 (Rate Limit)
                if response.status_code == 429:
                    self.logger.warning(f"Rate limited (429) on {url}. Sleeping for {config.RETRY_SLEEP}s...")
                    time.sleep(config.RETRY_SLEEP)
                    continue

                response.raise_for_status()
                return response

            except requests.exceptions.RequestException as e:
                self.logger.error(f"Error fetching {url}: {e}")
                if attempt == max_retries - 1:
                    # Log to the critical error report if we fail all retries
                    from utils import save_error
                    save_error(f"FAILED to fetch {url} after {max_retries} attempts: {e}", config.ERROR_LOG)
                    return None

        return None

    def get_navigation_links(self):
        """
        Fetches the homepage and extracts the navigation structure from the
        embedded VitePress JSON data.
        Returns a list of dictionaries: [{'title': 'Name', 'url': 'full_url'}]
        """
        self.logger.info("Fetching homepage to discover navigation links...")
        response = self._get_request(self.base_url)
        if not response:
            return []

        # Extract the JSON blob
        # Look for window.__VP_SITE_DATA__=deserializeFunctions(JSON.parse("..."));
        # The pattern usually matches the JSON string inside JSON.parse("...")
        # Since the content is inside a string passed to JSON.parse, we need to extract that string.
        # It handles escaped quotes.

        match = re.search(r'window\.__VP_SITE_DATA__=deserializeFunctions\(JSON\.parse\("((?:[^"\\]|\\.)*)"\)\)', response.text)

        links = []

        if match:
            try:
                # The regex captures the string content inside the quotes.
                # We need to unescape it to get valid JSON.
                # Use codecs.decode to unescape the string literal
                json_str_escaped = match.group(1)
                # This string is double-escaped in the JS source (e.g. \"title\")
                # We can try to just load it as a string first if it was a raw string literal,
                # but it's inside JSON.parse("HERE"), so it is a string representation of JSON.

                # Simple unescape:
                json_str = json_str_escaped.encode('utf-8').decode('unicode_escape')

                data = json.loads(json_str)

                # Navigate: themeConfig -> sidebar
                sidebar = data.get('themeConfig', {}).get('sidebar', [])

                # Sidebar can be a list of objects.
                # Each object has 'text' and 'link' (if it's a link) or 'items' (if it's a group).

                def extract_links(items):
                    found = []
                    for item in items:
                        if 'link' in item and item['link']:
                            full_url = urljoin(self.base_url, item['link'])
                            # Filter out external links (checking if they start with base_url or represent relative paths)
                            if full_url.startswith(self.base_url):
                                found.append({
                                    'title': self._clean_title(item.get('text', '')),
                                    'url': full_url
                                })

                        if 'items' in item:
                            found.extend(extract_links(item['items']))
                    return found

                links = extract_links(sidebar)
                self.logger.info(f"Discovered {len(links)} navigation links from JSON.")

            except (json.JSONDecodeError, AttributeError, UnicodeDecodeError) as e:
                self.logger.error(f"Failed to parse VitePress JSON data: {e}")
                # Fallback?
        else:
            self.logger.warning("Could not find __VP_SITE_DATA__ pattern. Falling back to HTML parsing.")
            soup = BeautifulSoup(response.text, 'lxml')
            # Look for sidebar links manually
            # This depends on the specific class names which might change,
            # but usually valid semantic HTML is present.
            # Try to find all links that look like internal pages
            for a in soup.find_all('a', href=True):
                href = a['href']
                if href.startswith('/') and not href.startswith('//'):
                    full_url = urljoin(self.base_url, href)
                    # Exclude assets or special links
                    if not any(x in href for x in ['.png', '.jpg', '.ico', '#']):
                         links.append({'title': a.get_text(strip=True), 'url': full_url})

            # Deduplicate by URL
            unique_links = {}
            for link in links:
                unique_links[link['url']] = link
            links = list(unique_links.values())

        return links

    def _clean_title(self, raw_title):
        """
        Cleans HTML tags (like emoji spans) from the title text.
        Example: '<span class="i-twemoji:books"></span> Beginners Guide' -> 'Beginners Guide'
        """
        if not raw_title:
            return "Unknown"
        # Remove HTML tags
        clean = re.sub(r'<[^>]+>', '', raw_title)
        return clean.strip()

    def process_image(self, img_url, unique_id):
        """
        Downloads, resizes, and converts an image to WebP.
        Saves it as assets/thumbnails/{unique_id}.webp.
        """
        if not img_url:
            return None

        # 1. Check if hosted on fmhy.net
        parsed = urlparse(img_url)
        if parsed.netloc and "fmhy.net" not in parsed.netloc:
            self.logger.info(f"Skipping external image: {img_url}")
            return None

        target_path = os.path.join(config.THUMBNAILS_DIR, f"{unique_id}.webp")

        # If already exists, skip (unless we want to force update, but let's save bandwidth)
        if os.path.exists(target_path):
            return f"{unique_id}.webp"

        try:
            self.logger.info(f"Processing image: {img_url}")
            response = self._get_request(img_url)
            if not response:
                return None

            # 2. Open image with Pillow
            img = Image.open(BytesIO(response.content))

            # 3. Resize (Max 150px width)
            if img.width > config.IMAGE_MAX_WIDTH:
                ratio = config.IMAGE_MAX_WIDTH / img.width
                new_height = int(img.height * ratio)
                img = img.resize((config.IMAGE_MAX_WIDTH, new_height), Image.Resampling.LANCZOS)

            # 4. Save as WebP
            img.save(target_path, "WEBP", quality=config.IMAGE_QUALITY)
            return f"{unique_id}.webp"

        except (requests.RequestException, UnidentifiedImageError, IOError) as e:
            self.logger.error(f"Failed to process image {img_url}: {e}")
            return None

    def parse_page(self, html_content, page_url):
        """
        Parses the HTML of a sub-page to extract resources.
        Returns a list of "Entry" dictionaries.
        """
        soup = BeautifulSoup(html_content, 'lxml')
        entries = []

        # FMHY structure:
        # Content is usually in <main> -> <div class="vp-doc"> -> <div>
        # We look for <h3> headers (Categories) and then the <ul> lists following them.

        main_content = soup.find('main')
        if not main_content:
            self.logger.warning(f"No <main> tag found on {page_url}")
            return []

        # Find all H2 and H3 headers
        headers = main_content.find_all(['h2', 'h3'])

        for header in headers:
            section_title = self._clean_title(header.get_text())

            # Iterate through siblings until the next header
            curr = header.next_sibling
            while curr:
                if curr.name in ['h2', 'h3']:
                    break

                if curr.name == 'ul':
                    # Parse the list
                    for li in curr.find_all('li'):
                        try:
                            # Extract Link
                            a_tag = li.find('a')
                            if not a_tag:
                                continue

                            link_url = a_tag.get('href')
                            if not link_url:
                                continue

                            # Handle relative URLs
                            if link_url.startswith('/'):
                                link_url = urljoin(self.base_url, link_url)

                            link_title = self._clean_title(a_tag.get_text())

                            # Extract Description
                            # The description is usually the text in the <li> that is NOT the <a> tag.
                            # We can get the full text and subtract the title, or navigate the DOM.
                            # "Title - Description" format is common.
                            full_text = li.get_text(strip=True)

                            # Simple clean: Remove title from full text
                            # Be careful with " - " separators
                            description = full_text.replace(a_tag.get_text(strip=True), "").strip()
                            # Remove leading " - " or "-" or ","
                            description = re.sub(r'^[\s\-\,]+', '', description)

                            unique_id = get_unique_id(link_url)

                            entry = {
                                "category": section_title,
                                "title": link_title,
                                "url": link_url,
                                "description": description,
                                "unique_id": unique_id,
                                "source_page": page_url
                            }

                            # Image Check (for next step, but placeholder logic here)
                            # Check if there is an image in the <li> or nearby
                            img_tag = li.find('img')
                            if img_tag:
                                entry['image_url'] = urljoin(self.base_url, img_tag.get('src'))

                            entries.append(entry)

                        except (AttributeError, TypeError) as e:
                            self.logger.error(f"Error parsing item in {section_title}: {e}")
                            continue

                curr = curr.next_sibling

        return entries
