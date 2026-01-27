import json
import os
import re
import glob
from datetime import datetime

# --- CONFIGURATION ---
DATA_DIR = "data/daily"
PUBLIC_DIR = "public"
OUTPUT_FILE = os.path.join(PUBLIC_DIR, "index.html")

# --- JS LOGIC ---
# Q1A: Typewriter Active | Q3B: Icon Only handled in HTML
JS_SCRIPT = """
<script>
    document.addEventListener('DOMContentLoaded', () => {
        // 1. HAMBURGER LOGIC
        const menuBtn = document.getElementById('menuToggle');
        const body = document.body;
        
        if (menuBtn) {
            menuBtn.addEventListener('click', () => {
                if (window.innerWidth >= 1024) {
                    body.classList.toggle('zen-mode');
                } else {
                    body.classList.toggle('menu-open');
                }
            });
        }

        // 2. SEARCH REVEAL
        const searchBtn = document.getElementById('searchToggle');
        const searchContainer = document.getElementById('searchContainer');
        const searchInput = document.getElementById('searchInput');

        if (searchBtn) {
            searchBtn.addEventListener('click', () => {
                searchContainer.classList.toggle('active');
                if (searchContainer.classList.contains('active')) {
                    searchInput.focus();
                }
            });
        }

        // 3. TYPEWRITER EFFECT (Q1A: Dynamic)
        const terms = ["Movies...", "AI Tools...", "Adblock...", "Linux ISOs...", "Streaming..."];
        let termIndex = 0;
        let charIndex = 0;
        let isDeleting = false;
        
        function type() {
            if (!searchInput) return;
            const currentTerm = terms[termIndex];
            
            if (isDeleting) {
                searchInput.placeholder = currentTerm.substring(0, charIndex - 1);
                charIndex--;
            } else {
                searchInput.placeholder = currentTerm.substring(0, charIndex + 1);
                charIndex++;
            }

            if (!isDeleting && charIndex === currentTerm.length) {
                isDeleting = true;
                setTimeout(type, 2000); 
            } else if (isDeleting && charIndex === 0) {
                isDeleting = false;
                termIndex = (termIndex + 1) % terms.length;
                setTimeout(type, 500);
            } else {
                setTimeout(type, isDeleting ? 50 : 100);
            }
        }
        
        type(); // Always run (No Low-End check)
    });
</script>
"""

# --- HTML FRAGMENTS ---
HTML_HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FMHY - The Abyssal Wiki</title>
    <link rel="stylesheet" href="../builder/style.css"> 
    <meta name="theme-color" content="#050505">
</head>
<body>
<div class="app-shell">
"""

HEADER = """
    <header class="site-header">
        <div class="header-left">
            <button id="menuToggle" class="menu-btn" aria-label="Toggle Menu">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <line x1="3" y1="12" x2="21" y2="12"></line>
                    <line x1="3" y1="6" x2="21" y2="6"></line>
                    <line x1="3" y1="18" x2="21" y2="18"></line>
                </svg>
            </button>
            <a href="#" class="brand">FMHY</a>
        </div>
        
        <div class="search-wrapper">
            <div id="searchContainer" class="search-input-container">
                <input type="text" id="searchInput" placeholder="Search...">
            </div>
            <button id="searchToggle" class="search-toggle-btn" title="Search">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="11" cy="11" r="8"></circle>
                    <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
                </svg>
            </button>
        </div>
    </header>
"""

# --- UTILITY FUNCTIONS ---
def get_latest_json():
    files = glob.glob(os.path.join(DATA_DIR, "*.json"))
    if not files: return None
    return max(files, key=os.path.getctime)

def clean_key(key):
    return key.replace('\u200b', '').strip()

def generate_id(key):
    return re.sub(r'[^a-z0-9]', '-', clean_key(key).lower())

def process_affiliate_link(url):
    # Q2B: BLOCKLIST REMOVED. All links allowed.
    return url

# --- BUILDER LOGIC ---
def build_site():
    print("Starting build process...")
    json_file = get_latest_json()
    if not json_file:
        print("ERROR: No JSON found.")
        return

    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 1. NAVIGATION
    sidebar_html = '<aside class="sidebar"><nav>'
    mobile_pills_html = '<nav class="mobile-nav"><a href="#" class="nav-pill">All</a>'
    
    categories = list(data.keys())
    for cat in categories:
        clean = clean_key(cat)
        cid = generate_id(cat)
        sidebar_html += f'<a href="#{cid}" class="sidebar-link">{clean}</a>'
        mobile_pills_html += f'<a href="#{cid}" class="nav-pill">{clean}</a>'

    sidebar_html += '</nav></aside>'
    mobile_pills_html += '</nav>'

    # 2. CONTENT
    content_html = '<main class="main-content">'
    for cat in categories:
        clean = clean_key(cat)
        cid = generate_id(cat)
        items = data[cat]
        if not items: continue

        content_html += f'<div id="{cid}" class="section-header"><h2 class="section-title">{clean}</h2></div><div class="grid">'

        for i, item in enumerate(items):
            title = item.get('title', 'Untitled')
            # Q2B: Affiliate links pass through directly
            url = process_affiliate_link(item.get('url', '#'))
            desc = item.get('description', '')[:200]
            
            content_html += f"""
            <a href="{url}" target="_blank" class="card" rel="noopener">
                <h3 class="card-title">{title}</h3>
                <p class="card-desc">{desc}</p>
            </a>
            """
            
            if (i + 1) % 6 == 0:
                content_html += '<div class="ad-card"><span class="ad-label">SPONSORED</span></div>'
        
        content_html += "</div>"
    
    content_html += '</main>'

    # 3. ASSEMBLE (Using f-strings to avoid ValueError)
    today = datetime.now().strftime("%Y-%m-%d")
    
    footer_html = f"""
    </div> </div> <footer style="text-align:center; padding: 4rem; color: #52525b; font-size: 0.8rem;">
        Last Updated: {today}
    </footer>
    {JS_SCRIPT}
    </body>
    </html>
    """

    final_html = HTML_HEAD + HEADER + mobile_pills_html + sidebar_html + content_html + footer_html
    
    os.makedirs(PUBLIC_DIR, exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(final_html)
    
    print(f"Build Complete: {OUTPUT_FILE}")

if __name__ == "__main__":
    build_site()
