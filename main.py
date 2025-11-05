import pandas as pd
import re
from collections import defaultdict
from urllib.parse import urlparse
from tkinter import Tk, filedialog
import json
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import time
import random
import sys
import argparse

category_keywords = {
    "Education": ["edu", "school", "college", "university", "study", "learning", "course", "academy"],
    "Government": ["gov", "usda", "census", "sec", "sba", "aphis"],
    "Technology": ["tech", "react", "stackoverflow", "sqlite", "unity", "w3schools"],
    "Business": ["business", "magazine", "worksource", "commerce"],
    "Science": ["arxiv", "endocrine", "aaalac", "aaha", "aalas"],
    "Language": ["rosettastone", "rhetoric"],
    "Math": ["math", "wamap", "prisonmath"],
    "Testing": ["accuplacer", "quizlet"],
    "News": ["apnews", "journalist"],
    "Support": ["sbctc", "studentaid", "vitalsource"]
}

# ---------- Config ----------
REPORTS_FILE = "site_reports.json"  # File to store user reports
CATEGORY_CHANGES_FILE = "reports/category_changes.json"  # File to store admin category changes
DESCRIPTIONS_FILE = "reports/site_descriptions.json"  # File to store site descriptions

# ---------- Command Line Arguments ----------
parser = argparse.ArgumentParser(description='Generate approved websites page')
parser.add_argument('--skip-descriptions', action='store_true', 
                   help='Skip generating website descriptions (faster generation)')
parser.add_argument('--generate-descriptions', action='store_true',
                   help='Generate website descriptions (slower but more informative)')
args = parser.parse_args()

# Determine if we should generate descriptions
GENERATE_DESCRIPTIONS = args.generate_descriptions or (not args.skip_descriptions and len(sys.argv) == 1)

# ---------- Helpers ----------
def normalize_url(raw: str) -> str:
    """Normalize URL by adding https:// if no scheme is present"""
    raw = str(raw).strip()
    if not raw:
        return raw
    # Prepend https:// if no scheme
    if not re.match(r'^[a-z]+://', raw, re.I):
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    if not parsed.netloc and parsed.path:  # e.g., "example.com"
        return f"https://{parsed.path}"
    return parsed.geturl()


def categorize(site_name, url):
    """Categorize sites based on keywords in name and URL"""
    combined = f"{site_name} {url}".lower()
    for category, keywords in category_keywords.items():
        if any(keyword in combined for keyword in keywords):
            return category
    return "Other"


def load_reports():
    """Load existing reports from JSON file"""
    try:
        with open(REPORTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return []
    except Exception as e:
        print(f"Warning: Could not load reports file: {e}")
        return []


def save_reports(reports):
    """Save reports to JSON file"""
    try:
        with open(REPORTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(reports, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Warning: Could not save reports file: {e}")


def load_category_changes():
    """Load admin category changes from JSON file"""
    try:
        with open(CATEGORY_CHANGES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return []
    except Exception as e:
        print(f"Warning: Could not load category changes file: {e}")
        return []


def save_category_changes(changes):
    """Save admin category changes to JSON file"""
    try:
        with open(CATEGORY_CHANGES_FILE, 'w', encoding='utf-8') as f:
            json.dump(changes, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Warning: Could not save category changes file: {e}")


def get_category_for_site(site_name, site_url, category_changes):
    """Get the category for a site, checking admin changes first"""
    # Check if there's an admin override for this site
    for change in category_changes:
        if (change.get('site_name') == site_name and 
            change.get('site_url') == site_url and 
            change.get('status') == 'applied'):
            return change.get('new_category')
    
    # Fall back to automatic categorization
    return categorize(site_name, site_url)


def load_descriptions():
    """Load existing site descriptions from JSON file"""
    try:
        with open(DESCRIPTIONS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"Warning: Could not load descriptions file: {e}")
        return {}


def save_descriptions(descriptions):
    """Save site descriptions to JSON file"""
    try:
        with open(DESCRIPTIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(descriptions, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Warning: Could not save descriptions file: {e}")


def analyze_website(url, site_name):
    """Analyze a website and generate a description"""
    try:
        # Add random delay to be respectful to servers
        time.sleep(random.uniform(1, 3))
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        }
        
        response = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.decompose()
        
        # Extract key information
        title = soup.find('title')
        title_text = title.get_text().strip() if title else ""
        
        # Look for meta description (multiple variations)
        meta_description = ""
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc:
            meta_description = meta_desc.get('content', '').strip()
        
        # Try Open Graph description
        if not meta_description:
            og_desc = soup.find('meta', attrs={'property': 'og:description'})
            if og_desc:
                meta_description = og_desc.get('content', '').strip()
        
        # Try Twitter card description
        if not meta_description:
            twitter_desc = soup.find('meta', attrs={'name': 'twitter:description'})
            if twitter_desc:
                meta_description = twitter_desc.get('content', '').strip()
        
        # Extract content from page - try multiple strategies
        content_elements = []
        
        # Strategy 1: Try semantic HTML5 elements
        main_content = soup.find('main') or soup.find('article') or soup.find('section')
        
        # Strategy 2: Try common content divs
        if not main_content:
            for selector in ['div.content', 'div.main-content', 'div.page-content', 'div#content', 'div#main']:
                main_content = soup.select_one(selector)
                if main_content:
                    break
        
        # Strategy 3: Try body if nothing else found
        if not main_content:
            main_content = soup.find('body')
        
        if main_content:
            # Get headings (more comprehensive)
            headings = main_content.find_all(['h1', 'h2', 'h3', 'h4'])
            for heading in headings[:5]:  # Get more headings
                text = heading.get_text().strip()
                # Clean up text
                text = re.sub(r'\s+', ' ', text)
                if text and 10 < len(text) < 250:
                    content_elements.append(text)
            
            # Get paragraphs (more comprehensive)
            paragraphs = main_content.find_all('p')
            for p in paragraphs[:5]:  # Get more paragraphs
                text = p.get_text().strip()
                # Clean up text
                text = re.sub(r'\s+', ' ', text)
                if text and 30 < len(text) < 500:
                    # Skip if it looks like navigation or footer
                    if not any(skip in text.lower() for skip in ['cookie', 'privacy', 'terms', 'copyright', 'menu', 'navigation']):
                        content_elements.append(text)
            
            # Try to get summary/intro text
            for tag in ['div.lead', 'div.intro', 'div.summary', 'p.lead', 'p.intro']:
                intro = main_content.select_one(tag)
                if intro:
                    text = intro.get_text().strip()
                    text = re.sub(r'\s+', ' ', text)
                    if text and 30 < len(text) < 400:
                        content_elements.insert(0, text)  # Put at front
        
        # Generate description based on available information
        description_parts = []
        
        # Priority 1: Meta description
        if meta_description and len(meta_description) > 15:
            description_parts.append(meta_description)
        
        # Priority 2: Content from page
        if not description_parts and content_elements:
            # Combine first few meaningful content elements
            combined_text = ' '.join(content_elements[:3])
            # Clean up
            combined_text = re.sub(r'\s+', ' ', combined_text)
            if len(combined_text) > 50:
                if len(combined_text) > 280:
                    combined_text = combined_text[:277] + "..."
                description_parts.append(combined_text)
        
        # Priority 3: Title (enhanced)
        if not description_parts and title_text and len(title_text) > 5:
            # Try to make title more descriptive
            if site_name and site_name.lower() not in title_text.lower():
                description_parts.append(f"{title_text} - {site_name}")
            else:
                description_parts.append(title_text)
        
        # Priority 4: Fallback with site name intelligence
        if not description_parts:
            domain = urlparse(url).netloc
            # Try to use site name more intelligently
            if site_name and len(site_name) > 3:
                description_parts.append(f"{site_name} - Educational resource ({domain})")
            else:
                description_parts.append(f"Educational resource website ({domain})")
        
        # Clean up and format the description
        description = ' '.join(description_parts)
        description = re.sub(r'\s+', ' ', description)  # Remove extra whitespace
        description = description.strip()
        
        # Remove HTML tags if any slipped through
        description = re.sub(r'<[^>]+>', '', description)
        
        # Ensure description is not too long
        if len(description) > 300:
            description = description[:297] + "..."
        
        return {
            'description': description,
            'title': title_text,
            'meta_description': meta_description,
            'status': 'success',
            'timestamp': datetime.now().isoformat()
        }
        
    except requests.exceptions.RequestException as e:
        # Better error handling - try to use site name
        domain = urlparse(url).netloc
        if site_name and len(site_name) > 3:
            fallback = f"{site_name} - Educational resource ({domain})"
        else:
            fallback = f"Educational resource ({domain})"
        return {
            'description': fallback,
            'title': site_name,
            'meta_description': '',
            'status': 'error',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }
    except Exception as e:
        domain = urlparse(url).netloc
        if site_name and len(site_name) > 3:
            fallback = f"{site_name} - Educational resource ({domain})"
        else:
            fallback = f"Educational resource ({domain})"
        return {
            'description': fallback,
            'title': site_name,
            'meta_description': '',
            'status': 'error',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }


def get_description_for_site(site_name, site_url, descriptions):
    """Get description for a site, generating if needed"""
    url_key = site_url
    
    if url_key in descriptions:
        return descriptions[url_key].get('description', f"Educational website ({urlparse(site_url).netloc})")
    
    # Generate new description
    print(f"🔍 Analyzing website: {site_name} ({site_url})")
    analysis = analyze_website(site_url, site_name)
    
    # Store the description
    descriptions[url_key] = analysis
    
    return analysis.get('description', f"Educational website ({urlparse(site_url).netloc})")


def get_report_count_for_site(site_url, reports):
    """Get the number of reports for a specific site"""
    return sum(1 for report in reports if report.get('site_url') == site_url)


def escape_html(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# ---------- GUI file picker ----------
Tk().withdraw()
file_path = filedialog.askopenfilename(
    title="Select the Whitelist Excel File",
    filetypes=[("Excel files", "*.xlsx *.xls")]
)

if not file_path:
    print("No file selected. Exiting.")
    raise SystemExit


# ---------- Load Excel ----------
df = pd.read_excel(file_path, usecols=[0, 1], engine="openpyxl")

# Ensure headers exist; allow best-effort rename
expected_cols = {"Site Name", "URL"}
if not expected_cols.issubset(set(df.columns)):
    col_map = {}
    for c in df.columns:
        lc = str(c).strip().lower()
        if lc in ("site name", "name", "title"):
            col_map[c] = "Site Name"
        elif lc in ("url", "link", "website"):
            col_map[c] = "URL"
    if col_map:
        df = df.rename(columns=col_map)

df.dropna(subset=["Site Name", "URL"], inplace=True)


# ---------- Process ----------
categorized_sites = defaultdict(list)
category_changes = load_category_changes()

if GENERATE_DESCRIPTIONS:
    descriptions = load_descriptions()
    print("🔍 Loading and analyzing website descriptions...")
    print("⏳ This may take several minutes for new websites...")
    print("💡 Tip: Use --skip-descriptions for faster generation")
else:
    descriptions = {}
    print("⚡ Skipping description generation for faster processing...")
    print("💡 Use --generate-descriptions to include website descriptions")

total_sites = len(df)
processed = 0

for _, row in df.iterrows():
    site_name = str(row["Site Name"]).strip()
    raw_url = str(row["URL"]).strip()
    
    # Skip sites that have been removed (check for "removed" text in name or URL)
    if "removed" in site_name.lower() or "removed" in raw_url.lower():
        print(f"⏭️  Skipping removed site: {site_name}")
        continue
    
    # Normalize URL for display
    display_url = normalize_url(raw_url)
    
    # Get category (checking admin changes first)
    category = get_category_for_site(site_name, display_url, category_changes)
    
    # Get description for the site (if enabled)
    if GENERATE_DESCRIPTIONS:
        description = get_description_for_site(site_name, display_url, descriptions)
    else:
        description = f"Educational website ({urlparse(display_url).netloc})"
    
    # Add to categorized sites with description
    categorized_sites[category].append((site_name, display_url, description))
    
    # Progress feedback
    processed += 1
    if processed % 10 == 0 or processed == total_sites:
        print(f"📊 Processed {processed}/{total_sites} websites...")

# Save descriptions after processing (if generated)
if GENERATE_DESCRIPTIONS:
    save_descriptions(descriptions)
    print("✅ Website descriptions saved!")


# ---------- Generate HTML ----------
total_sites = sum(len(v) for v in categorized_sites.values())

html_content = f"""
<html>
<head>
    <meta charset="utf-8">
    <title>Approved Websites for Incarcerated Students</title>
    <style>
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
            margin: 0; 
            padding: 20px; 
            background-color: #f5f5f5;
            line-height: 1.6;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }}
        .header h1 {{ margin: 0; font-size: 2.2em; font-weight: 300; }}
        .header p {{ margin: 10px 0 0 0; opacity: 0.9; }}
        .layout {{
            display: flex;
            min-height: 100vh;
        }}
        .sidebar {{
            position: fixed;
            top: 0;
            left: 0;
            width: 280px;
            height: 100vh;
            background-color: #f8f9fa;
            border-right: 1px solid #e9ecef;
            overflow-y: auto;
            z-index: 100;
        }}
        .sidebar-content {{
            padding: 20px;
        }}
        .content {{
            margin-left: 280px;
            padding: 30px;
            width: calc(100% - 280px);
        }}
        .search-section {{
            margin-bottom: 25px;
        }}
        .search-section h3 {{
            margin: 0 0 15px 0;
            color: #495057;
            font-size: 1.1em;
        }}
        .search-section input {{
            width: 100%;
            padding: 12px;
            border: 1px solid #ddd;
            border-radius: 6px;
            font-size: 16px;
            box-sizing: border-box;
        }}
        .categories-section {{
            margin-bottom: 20px;
        }}
        .categories-section h3 {{
            margin: 0 0 15px 0;
            color: #495057;
            font-size: 1.1em;
        }}
        .category-list {{
            list-style: none;
            padding: 0;
            margin: 0;
        }}
        .category-item {{
            margin-bottom: 8px;
        }}
        .category-link {{
            display: block;
            padding: 12px 15px;
            background: white;
            border: 1px solid #e9ecef;
            border-radius: 6px;
            text-decoration: none;
            color: #495057;
            transition: all 0.3s ease;
            position: relative;
        }}
        .category-link:hover {{
            background: #e9ecef;
            transform: translateX(5px);
            text-decoration: none;
            color: #495057;
        }}
        .category-link.active {{
            background: #007bff;
            color: white;
            border-color: #007bff;
        }}
        .category-name {{
            font-weight: 500;
            margin-bottom: 4px;
        }}
        .category-count {{
            background: #6c757d;
            color: white;
            border-radius: 12px;
            padding: 2px 8px;
            font-size: 0.8em;
            font-weight: bold;
            float: right;
        }}
        .category-link.active .category-count {{
            background: rgba(255,255,255,0.3);
        }}
        .site-list {{
            list-style: none;
            padding: 0;
        }}
        .site-item {{
            background: white;
            border: 1px solid #e9ecef;
            border-radius: 8px;
            margin-bottom: 15px;
            padding: 20px;
            transition: all 0.3s ease;
        }}
        .site-item:hover {{
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .site-name {{
            font-size: 1.2em;
            font-weight: 600;
            color: #212529;
            margin-bottom: 8px;
        }}
        .site-url {{
            color: #6c757d;
            font-size: 0.95em;
            margin-bottom: 10px;
            word-break: break-all;
        }}
        .site-description {{
            color: #495057;
            font-size: 0.9em;
            line-height: 1.4;
            margin-bottom: 15px;
            padding: 10px;
            background: #f8f9fa;
            border-radius: 6px;
            border-left: 3px solid #007bff;
        }}
        .site-actions {{
            display: flex;
            gap: 10px;
            align-items: center;
        }}
        .visit-btn {{
            background: #28a745;
            color: white;
            padding: 8px 16px;
            border: none;
            border-radius: 6px;
            text-decoration: none;
            font-size: 0.9em;
            transition: background 0.3s ease;
        }}
        .visit-btn:hover {{
            background: #218838;
            text-decoration: none;
            color: white;
        }}
        .category-section {{
            margin-bottom: 40px;
        }}
        .category-title {{
            color: #495057;
            border-bottom: 2px solid #e9ecef;
            padding-bottom: 10px;
            margin: 0 0 20px 0;
            font-size: 1.5em;
        }}
        .stats {{
            background: #e9ecef;
            padding: 15px;
            border-radius: 8px;
            margin-top: 20px;
            font-size: 0.9em;
            line-height: 1.4;
        }}
        .hidden {{ display: none; }}
    </style>
    <script>
        function filterSites() {{
            var input = document.getElementById("searchInput").value.toLowerCase();
            var items = document.querySelectorAll(".site-item");
            var hasResults = false;
            
            items.forEach(function(item) {{
                var text = item.textContent.toLowerCase();
                if (text.includes(input)) {{
                    item.classList.remove("hidden");
                    hasResults = true;
                }} else {{
                    item.classList.add("hidden");
                }}
            }});
            
            // Show/hide category sections based on results
            var categories = document.querySelectorAll(".category-section");
            categories.forEach(function(category) {{
                var visibleItems = category.querySelectorAll(".site-item:not(.hidden)");
                if (visibleItems.length > 0 || input === "") {{
                    category.classList.remove("hidden");
                }} else {{
                    category.classList.add("hidden");
                }}
            }});
        }}
        
        function scrollToCategory(categoryId) {{
            var element = document.getElementById(categoryId);
            if (element) {{
                element.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
                
                // Update active category
                var links = document.querySelectorAll(".category-link");
                links.forEach(function(link) {{
                    link.classList.remove("active");
                }});
                document.querySelector('a[href="#' + categoryId + '"]').classList.add("active");
            }}
        }}
        
        // Update active category on scroll
        window.addEventListener('scroll', function() {{
            var categories = document.querySelectorAll(".category-section");
            var scrollPos = window.scrollY + 100;
            
            categories.forEach(function(category) {{
                var categoryTop = category.offsetTop;
                var categoryBottom = categoryTop + category.offsetHeight;
                
                if (scrollPos >= categoryTop && scrollPos < categoryBottom) {{
                    var categoryId = category.id;
                    var links = document.querySelectorAll(".category-link");
                    links.forEach(function(link) {{
                        link.classList.remove("active");
                    }});
                    var activeLink = document.querySelector('a[href="#' + categoryId + '"]');
                    if (activeLink) {{
                        activeLink.classList.add("active");
                    }}
                }}
            }});
        }});
    </script>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Approved Websites</h1>
            <p>For Incarcerated Students</p>
        </div>
        
        <div class="layout">
            <div class="sidebar">
                <div class="sidebar-content">
                    <div class="search-section">
                        <h3>Search Websites</h3>
                        <input type="text" id="searchInput" onkeyup="filterSites()" placeholder="Type to search websites..." />
                    </div>
                    
                    <div class="categories-section">
                        <h3>Categories</h3>
                        <ul class="category-list">
"""

# Generate category sidebar links
for category in sorted(categorized_sites.keys()):
    count = len(categorized_sites[category])
    html_content += f"""
                            <li class="category-item">
                                <a href="#{escape_html(category)}" class="category-link" onclick="scrollToCategory('{escape_html(category)}'); return false;">
                                    <span class="category-name">{escape_html(category)}</span>
                                    <span class="category-count">{count}</span>
                                </a>
                            </li>"""

html_content += f"""
                        </ul>
                    </div>
                    
                    <div class="stats">
                        <strong>Total Websites:</strong> {total_sites}<br>
                        <strong>Categories:</strong> {len(categorized_sites)}<br>
                        <strong>Last Updated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M')}
                    </div>
                </div>
            </div>
            
            <div class="content">
"""

# Generate site listings by category
for category in sorted(categorized_sites.keys()):
    html_content += f"""
                <div id="{escape_html(category)}" class="category-section">
                    <h2 class="category-title">{escape_html(category)}</h2>
                    <ul class="site-list">"""
    
    for site_name, url, description in sorted(categorized_sites[category], key=lambda x: x[0].lower()):
        html_content += f"""
                        <li class="site-item">
                            <div class="site-name">{escape_html(site_name)}</div>
                            <div class="site-url">{escape_html(url)}</div>
                            <div class="site-description">{escape_html(description)}</div>
                            <div class="site-actions">
                                <a href="{escape_html(url)}" target="_blank" class="visit-btn">Visit Site</a>
                            </div>
                        </li>"""
    
    html_content += """
                    </ul>
                </div>"""

html_content += """
        </div>
    </div>
</body>
</html>
"""

with open("approved_websites.html", "w", encoding="utf-8") as f:
    f.write(html_content)

print("✅ Website listing generated successfully!")
print(f"📄 HTML page saved as 'approved_websites.html'")
print(f"📊 Total websites: {total_sites}")
print(f"📁 Categories: {len(categorized_sites)}")
print("\n🎯 Users can now:")
print("   • Browse websites by category")
print("   • Search for specific sites")