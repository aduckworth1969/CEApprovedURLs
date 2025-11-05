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
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extract key information
        title = soup.find('title')
        title_text = title.get_text().strip() if title else ""
        
        # Look for meta description
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        meta_description = meta_desc.get('content', '').strip() if meta_desc else ""
        
        # Extract main content from common elements
        content_elements = []
        
        # Try to find main content areas
        main_content = soup.find('main') or soup.find('article') or soup.find('div', class_=re.compile(r'content|main|body', re.I))
        if main_content:
            # Get text from headings and paragraphs
            headings = main_content.find_all(['h1', 'h2', 'h3'])
            paragraphs = main_content.find_all('p')
            
            for heading in headings[:3]:  # First 3 headings
                text = heading.get_text().strip()
                if text and len(text) < 200:
                    content_elements.append(text)
            
            for p in paragraphs[:2]:  # First 2 paragraphs
                text = p.get_text().strip()
                if text and len(text) > 20 and len(text) < 300:
                    content_elements.append(text)
        
        # Generate description based on available information
        description_parts = []
        
        if meta_description and len(meta_description) > 10:
            description_parts.append(meta_description)
        elif content_elements:
            # Combine first few content elements
            combined_text = ' '.join(content_elements[:2])
            if len(combined_text) > 200:
                combined_text = combined_text[:200] + "..."
            description_parts.append(combined_text)
        elif title_text and len(title_text) > 10:
            description_parts.append(f"Website: {title_text}")
        
        if not description_parts:
            # Fallback based on site name and URL
            domain = urlparse(url).netloc
            description_parts.append(f"Educational resource website ({domain})")
        
        # Clean up and format the description
        description = ' '.join(description_parts)
        description = re.sub(r'\s+', ' ', description)  # Remove extra whitespace
        description = description.strip()
        
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
        return {
            'description': f"Educational website ({urlparse(url).netloc})",
            'title': site_name,
            'meta_description': '',
            'status': 'error',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }
    except Exception as e:
        return {
            'description': f"Educational resource ({urlparse(url).netloc})",
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
reports = load_reports()
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
        .report-btn {{
            background: #dc3545;
            color: white;
            padding: 8px 16px;
            border: none;
            border-radius: 6px;
            font-size: 0.9em;
            cursor: pointer;
            transition: background 0.3s ease;
        }}
        .report-btn:hover {{
            background: #c82333;
        }}
        .suggest-btn {{
            background: #17a2b8;
            color: white;
            padding: 8px 16px;
            border: none;
            border-radius: 6px;
            font-size: 0.9em;
            cursor: pointer;
            transition: background 0.3s ease;
        }}
        .suggest-btn:hover {{
            background: #138496;
        }}
        .report-count {{
            background: #ffc107;
            color: #212529;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.8em;
            font-weight: bold;
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
        
        function showReportForm(siteName, siteUrl) {{
            var form = document.getElementById("reportForm");
            var siteNameField = document.getElementById("siteName");
            var siteUrlField = document.getElementById("siteUrl");
            
            siteNameField.value = siteName;
            siteUrlField.value = siteUrl;
            form.style.display = "block";
        }}
        
        function hideReportForm() {{
            document.getElementById("reportForm").style.display = "none";
        }}
        
        function showSuggestForm(siteName, siteUrl, currentCategory) {{
            var form = document.getElementById("suggestForm");
            var siteNameField = document.getElementById("suggestSiteName");
            var siteUrlField = document.getElementById("suggestSiteUrl");
            var currentCategoryField = document.getElementById("currentCategory");
            var currentCategoryDisplay = document.getElementById("currentCategoryDisplay");
            
            siteNameField.value = siteName;
            siteUrlField.value = siteUrl;
            currentCategoryField.value = currentCategory;
            currentCategoryDisplay.value = currentCategory;
            form.style.display = "block";
        }}
        
        function hideSuggestForm() {{
            document.getElementById("suggestForm").style.display = "none";
        }}
        
        function submitSuggest() {{
            var siteName = document.getElementById("suggestSiteName").value;
            var siteUrl = document.getElementById("suggestSiteUrl").value;
            var currentCategory = document.getElementById("currentCategory").value;
            var suggestedCategory = document.getElementById("suggestedCategory").value;
            var reason = document.getElementById("suggestReason").value;
            
            if (!suggestedCategory) {{
                alert("Please select a suggested category.");
                return;
            }}
            
            // Create suggestion object
            var suggestion = {{
                site_name: siteName,
                site_url: siteUrl,
                current_category: currentCategory,
                suggested_category: suggestedCategory,
                reason: reason,
                timestamp: new Date().toISOString(),
                user_agent: navigator.userAgent,
                suggestion_id: 'suggest_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9)
            }};
            
            // Send suggestion to server
            fetch('/submit_suggestion', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json',
                }},
                body: JSON.stringify(suggestion)
            }})
            .then(response => response.json())
            .then(data => {{
                if (data.success) {{
                    alert("Thank you for your category suggestion. IT staff will review it.");
                    hideSuggestForm();
                    // Reset form fields manually
                    document.getElementById("suggestedCategory").value = "";
                    document.getElementById("suggestReason").value = "";
                }} else {{
                    alert("There was an error submitting your suggestion. Please try again.");
                }}
            }})
            .catch(error => {{
                console.error('Error submitting suggestion:', error);
                alert("Unable to submit suggestion. Please check your connection and try again.");
            }});
        }}
        
        function submitReport() {{
            var siteName = document.getElementById("siteName").value;
            var siteUrl = document.getElementById("siteUrl").value;
            var issueType = document.getElementById("issueType").value;
            var description = document.getElementById("description").value;
            
            if (!issueType) {{
                alert("Please select an issue type.");
                return;
            }}
            
            // Create report object
            var report = {{
                site_name: siteName,
                site_url: siteUrl,
                issue_type: issueType,
                description: description,
                timestamp: new Date().toISOString(),
                user_agent: navigator.userAgent,
                report_id: 'report_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9)
            }};
            
            // Send report to server (Python script will handle saving)
            fetch('/submit_report', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json',
                }},
                body: JSON.stringify(report)
            }})
            .then(response => response.json())
            .then(data => {{
                if (data.success) {{
                    alert("Thank you for reporting this issue. IT staff will review your feedback.");
                    hideReportForm();
                    // Reset form fields manually
                    document.getElementById("issueType").value = "";
                    document.getElementById("description").value = "";
                }} else {{
                    alert("There was an error submitting your report. Please try again.");
                }}
            }})
            .catch(error => {{
                console.error('Error submitting report:', error);
                alert("Unable to submit report. Please check your connection and try again.");
            }});
        }}
    </script>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Approved Websites</h1>
            <p>For Incarcerated Students - Report issues to help us improve</p>
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
        report_count = get_report_count_for_site(url, reports)
        report_badge = f"<span class='report-count'>{report_count} reports</span>" if report_count > 0 else ""
        
        html_content += f"""
                        <li class="site-item">
                            <div class="site-name">{escape_html(site_name)}</div>
                            <div class="site-url">{escape_html(url)}</div>
                            <div class="site-description">{escape_html(description)}</div>
                            <div class="site-actions">
                                <a href="{escape_html(url)}" target="_blank" class="visit-btn">Visit Site</a>
                                <button class="report-btn" onclick="showReportForm('{escape_html(site_name)}', '{escape_html(url)}')">Report Issue</button>
                                <button class="suggest-btn" onclick="showSuggestForm('{escape_html(site_name)}', '{escape_html(url)}', '{escape_html(category)}')">Suggest Category</button>
                                {report_badge}
                            </div>
                        </li>"""
    
    html_content += """
                    </ul>
                </div>"""

html_content += """
        </div>
        
        <!-- Report Form Modal -->
        <div id="reportForm" style="display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 1000;">
            <div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); background: white; padding: 30px; border-radius: 8px; width: 90%; max-width: 500px;">
                <h3>Report Website Issue</h3>
                <form>
                    <input type="hidden" id="siteName" />
                    <input type="hidden" id="siteUrl" />
                    
                    <div style="margin-bottom: 15px;">
                        <label><strong>Issue Type:</strong></label><br>
                        <select id="issueType" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px;">
                            <option value="">Select an issue type...</option>
                            <option value="site_not_loading">Site not loading</option>
                            <option value="site_blocked">Site blocked/filtered</option>
                            <option value="content_issues">Content issues</option>
                            <option value="slow_loading">Slow loading</option>
                            <option value="broken_links">Broken links</option>
                            <option value="other">Other technical problem</option>
                        </select>
                    </div>
                    
                    <div style="margin-bottom: 20px;">
                        <label><strong>Description (optional):</strong></label><br>
                        <textarea id="description" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; height: 80px;" placeholder="Describe the issue you encountered..."></textarea>
                    </div>
                    
                    <div style="text-align: right;">
                        <button type="button" onclick="hideReportForm()" style="padding: 8px 16px; margin-right: 10px; border: 1px solid #ddd; background: white; border-radius: 4px;">Cancel</button>
                        <button type="button" onclick="submitReport()" style="padding: 8px 16px; background: #dc3545; color: white; border: none; border-radius: 4px;">Submit Report</button>
                    </div>
                </form>
            </div>
        </div>
        
        <!-- Category Suggestion Form Modal -->
        <div id="suggestForm" style="display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 1000;">
            <div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); background: white; padding: 30px; border-radius: 8px; width: 90%; max-width: 500px;">
                <h3>Suggest Better Category</h3>
                <form>
                    <input type="hidden" id="suggestSiteName" />
                    <input type="hidden" id="suggestSiteUrl" />
                    <input type="hidden" id="currentCategory" />
                    
                    <div style="margin-bottom: 15px;">
                        <label><strong>Current Category:</strong></label><br>
                        <input type="text" id="currentCategoryDisplay" readonly style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; background: #f8f9fa;">
                    </div>
                    
                    <div style="margin-bottom: 15px;">
                        <label><strong>Suggested Category:</strong></label><br>
                        <select id="suggestedCategory" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px;">
                            <option value="">Select a better category...</option>
                            <option value="Education">Education</option>
                            <option value="Government">Government</option>
                            <option value="Technology">Technology</option>
                            <option value="Business">Business</option>
                            <option value="Science">Science</option>
                            <option value="Language">Language</option>
                            <option value="Math">Math</option>
                            <option value="Testing">Testing</option>
                            <option value="News">News</option>
                            <option value="Support">Support</option>
                            <option value="Other">Other</option>
                        </select>
                    </div>
                    
                    <div style="margin-bottom: 20px;">
                        <label><strong>Reason (optional):</strong></label><br>
                        <textarea id="suggestReason" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; height: 80px;" placeholder="Why do you think this category is better?"></textarea>
                    </div>
                    
                    <div style="text-align: right;">
                        <button type="button" onclick="hideSuggestForm()" style="padding: 8px 16px; margin-right: 10px; border: 1px solid #ddd; background: white; border-radius: 4px;">Cancel</button>
                        <button type="button" onclick="submitSuggest()" style="padding: 8px 16px; background: #17a2b8; color: white; border: none; border-radius: 4px;">Submit Suggestion</button>
                    </div>
                </form>
            </div>
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
print(f"📝 Reports will be stored in: {REPORTS_FILE}")
print("\n🎯 Users can now:")
print("   • Browse websites by category")
print("   • Search for specific sites")
print("   • Report issues with websites")
print("   • View report counts for each site")