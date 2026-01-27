import json
import os
import re
import glob
from datetime import datetime

# --- CONFIGURATION ---
DATA_DIR = "data/daily"
PUBLIC_DIR = "public"
OUTPUT_FILE = os.path.join(PUBLIC_DIR, "index.html")

# --- HTML TEMPLATES ---
HTML_HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FMHY - The Abyssal Wiki</title>
    <link rel="stylesheet" href="../builder/style.css"> 
    <meta name="theme-color" content="#09090b">
</head>
<body>
<div class="app-shell">
"""

HEADER = """
    <header class="site-header">
        <a href="#" class="brand">FMHY</a>
        <div class="search-container">
            <input type="text" placeholder="Search resources...">
        </div>
        <div class="actions" style="opacity:0.5; font-size:0.9rem;">v2.0</div>
    </header>
"""

FOOTER = """
</div> </div> <footer style="text-align:center; padding: 4rem; color: #52525b; font-size: 0.8rem;">
    Last Updated: {date}
</footer>
</body>
</html>
"""

# --- UTILITY FUNCTIONS ---

def get_latest_json():
    """Finds the most recent JSON file in data/daily."""
    files = glob.glob(os.path.join(DATA_DIR, "*.json"))
    if not files:
        print("CRITICAL ERROR: No data files found in data/daily/")
        return None
    # Sort by filename (date format YYYY-MM-DD ensures correct sort)
    latest = max(files, key=os.path.getctime)
    print(f"Loading data source: {latest}")
    return latest

def clean_key(key):
    """Removes invisible chars and spaces for ID generation."""
    # Remove Zero Width Space (\u200b) and strip
    cleaned = key.replace('\u200b', '').strip()
    return cleaned

def generate_id(key):
    """Converts a category name to a URL-safe ID."""
    return re.sub(r'[^a-z0-9]', '-', clean_key(key).lower())

def process_affiliate_link(url):
    """Swaps affiliate links (Placeholder Logic)."""
    if any(x in url for x in ["nordvpn", "surfshark", "proton"]):
        return "#affiliate-placeholder"
    return url

# --- BUILDER LOGIC ---

def build_site():
    json_file = get_latest_json()
    if not json_file:
        return

    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 1. GENERATE NAVIGATION LISTS
    sidebar_html = '<aside class="sidebar"><nav>'
    mobile_pills_html = '<nav class="mobile-nav">'
    
    # Add "All" button
    mobile_pills_html += '<a href="#" class="nav-pill">All</a>'
    
    categories = list(data.keys())
    
    for cat in categories:
        clean_name = clean_key(cat)
        cat_id = generate_id(cat)
        
        # Sidebar Link
        sidebar_html += f'<a href="#{cat_id}" class="sidebar-link">{clean_name}</a>'
        # Mobile Pill
        mobile_pills_html += f'<a href="#{cat_id}" class="nav-pill">{clean_name}</a>'

    sidebar_html += '</nav></aside>'
    mobile_pills_html += '</nav>'

    # 2. GENERATE MAIN CONTENT
    content_html = '<main class="main-content">'
    
    for cat in categories:
        clean_name = clean_key(cat)
        cat_id = generate_id(cat)
        items = data[cat]
        
        if not items: 
            continue

        # Section Header
        content_html += f"""
        <div id="{cat_id}" class="section-header">
            <h2 class="section-title">{clean_name}</h2>
        </div>
        <div class="grid">
        """

        # Cards Loop
        for i, item in enumerate(items):
            title = item.get('title', 'Untitled')
            url = process_affiliate_link(item.get('url', '#'))
            desc = item.get('description', '')[:200] # Truncate

            # Card HTML
            content_html += f"""
            <a href="{url}" target="_blank" class="card" rel="noopener">
                <h3 class="card-title">{title}</h3>
                <p class="card-desc">{desc}</p>
            </a>
            """

            # Ad Injection (Every 6 cards)
            if (i + 1) % 6 == 0:
                content_html += """
                <div class="ad-card">
                    <span class="ad-label">SPONSORED</span>
                </div>
                """
        
        content_html += "</div>" # End Grid

    content_html += '</main>'

    # 3. ASSEMBLE FULL HTML
    final_html = HTML_HEAD + HEADER + mobile_pills_html + sidebar_html + content_html + FOOTER.format(date=datetime.now().strftime("%Y-%m-%d"))

    # 4. WRITE TO FILE
    os.makedirs(PUBLIC_DIR, exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(final_html)
    
    print(f"Build Complete: {OUTPUT_FILE}")

if __name__ == "__main__":
    build_site()
