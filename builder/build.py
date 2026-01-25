import os
import json
import glob
import datetime

def main():
    # Define paths relative to this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(script_dir)
    data_dir = os.path.join(root_dir, 'data', 'daily')
    public_dir = os.path.join(root_dir, 'public')

    # Ensure public directory exists
    os.makedirs(public_dir, exist_ok=True)

    # Find the most recent JSON file
    json_files = glob.glob(os.path.join(data_dir, '*.json'))
    if not json_files:
        print(f"Error: No data files found in {data_dir}")
        return

    latest_file = max(json_files, key=os.path.getctime)
    print(f"Processing file: {latest_file}")

    try:
        with open(latest_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
        return
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    # HTML Header
    html_content = [
        "<!DOCTYPE html>",
        "<html lang='en'>",
        "<head>",
        "    <meta charset='UTF-8'>",
        "    <meta name='viewport' content='width=device-width, initial-scale=1.0'>",
        "    <title>Daily Update</title>",
        "    <link rel='stylesheet' href='style.css'>",
        "</head>",
        "<body>",
        "    <div class='container'>",
        "        <h1>Latest Updates</h1>",
        "        <div class='grid'>"
    ]

    items_list = []
    if isinstance(data, list):
        items_list = data
    elif isinstance(data, dict):
        # Flatten dictionary of lists
        for category, items in data.items():
            if isinstance(items, list):
                items_list.extend(items)
            elif isinstance(items, dict): # Should not happen based on JSON but for safety
                 items_list.append(items)

    item_count = 0

    for item in items_list:
        if not isinstance(item, dict):
            continue

        item_count += 1

        # Extract fields (mapping from observed JSON structure)
        # Observed: title, description, url
        title = item.get('title', item.get('header', 'Untitled')).replace('\u200b', '')
        desc = item.get('description', '').replace('\u200b', '')

        # Normalize links
        links = []
        if 'url' in item:
            links.append({'url': item['url'], 'text': 'Visit'})
        elif 'links' in item:
            # If it uses the other schema
            links = item['links']

        # Process Links for Affiliate Swap
        processed_links_html = []

        for link in links:
            url = ""
            label = "Visit"

            if isinstance(link, dict):
                url = link.get('url', '')
                label = link.get('text', link.get('title', 'Visit'))
            elif isinstance(link, str):
                url = link

            if not url:
                continue

            # Affiliate Swap
            lower_url = url.lower()
            if "nordvpn" in lower_url:
                url = "#affiliate-nordvpn"
            elif "proton" in lower_url:
                url = "#affiliate-proton"
            elif "surfshark" in lower_url:
                url = "#affiliate-surfshark"

            processed_links_html.append(f"<a href='{url}' target='_blank'>{label}</a>")

        # Card HTML
        html_content.append(f"""
            <div class='card glass'>
                <h2>{title}</h2>
                <p>{desc}</p>
                <div class='links'>
                    {' '.join(processed_links_html)}
                </div>
            </div>
        """)

        # Ad Injection every 6th item
        if item_count % 6 == 0:
            html_content.append("""
                <div class='card glass ad-card'>
                    <h2>Sponsored</h2>
                    <p>Check out our partners for exclusive deals!</p>
                </div>
            """)

    # Close HTML
    html_content.extend([
        "        </div>",
        "    </div>",
        "</body>",
        "</html>"
    ])

    # Write output
    output_path = os.path.join(public_dir, 'index.html')
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(html_content))
        print(f"Successfully generated {output_path}")
    except Exception as e:
        print(f"Error writing output file: {e}")

if __name__ == "__main__":
    main()
