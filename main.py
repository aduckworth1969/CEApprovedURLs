import pandas as pd
import socket
from collections import defaultdict
from urllib.parse import urlparse
from tkinter import Tk, filedialog

# GUI file picker
Tk().withdraw()
file_path = filedialog.askopenfilename(
    title="Select the Whitelist Excel File",
    filetypes=[("Excel files", "*.xlsx *.xls")]
)

if not file_path:
    print("No file selected. Exiting.")
    exit()

# Load Excel file
df = pd.read_excel(file_path, usecols=[0, 1], engine="openpyxl")
df.dropna(subset=["Site Name", "URL"], inplace=True)

# Define categories
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

def categorize(site_name, url):
    combined = f"{site_name} {url}".lower()
    for category, keywords in category_keywords.items():
        if any(keyword in combined for keyword in keywords):
            return category
    return "Other"

def is_reachable(url):
    try:
        hostname = urlparse(url).netloc
        socket.gethostbyname(hostname)
        return True, ""
    except Exception as e:
        return False, str(e)

# Organize URLs
categorized_sites = defaultdict(list)
non_working_sites = []

for _, row in df.iterrows():
    site_name = row["Site Name"]
    url = row["URL"]
    category = categorize(site_name, url)
    reachable, reason = is_reachable(url)
    if reachable:
        categorized_sites[category].append((site_name, url))
    else:
        non_working_sites.append((site_name, url, reason))

# Generate HTML
html_content = """
<html>
<head>
    <title>Approved Websites</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        h1 { text-align: center; }
        .sidebar {
            position: fixed;
            top: 20px;
            left: 20px;
            width: 200px;
            background-color: #f0f0f0;
            padding: 10px;
            border: 1px solid #ccc;
        }
        .content {
            margin-left: 240px;
        }
        ul { list-style-type: none; padding-left: 0; }
        li { margin-bottom: 5px; }
        a { text-decoration: none; color: blue; }
        a:hover { text-decoration: underline; }
        #searchBar {
            margin-bottom: 20px;
        }
    </style>
    <script>
        function filterSites() {
            var input = document.getElementById("searchInput").value.toLowerCase();
            var items = document.querySelectorAll(".working-site");
            items.forEach(function(item) {
                if (item.textContent.toLowerCase().includes(input)) {
                    item.style.display = "";
                } else {
                    item.style.display = "none";
                }
            });
        }
    </script>
</head>
<body>
    <div class="sidebar">
        <h3>Categories</h3>
        <ul>
"""

# Sidebar links
for category in sorted(categorized_sites.keys()):
    html_content += f"<li><a href='#{category}'>{category}</a></li>"

html_content += """
        </ul>
    </div>
    <div class="content">
        <h1>Approved Websites for Incarcerated Students</h1>
        <div id="searchBar">
            <label for="searchInput"><strong>Search Working Sites:</strong></label><br>
            <input type="text" id="searchInput" onkeyup="filterSites()" placeholder="Type to search...">
        </div>
"""

# Working sites
for category in sorted(categorized_sites.keys()):
    html_content += f"<h2 id='{category}'>{category}</h2><ul>"
    for site_name, url in categorized_sites[category]:
        html_content += f"<li class='working-site'><a href='{url}' target='_blank'>{site_name}</a> - {url}</li>"
    html_content += "</ul>"

# Non-working sites
html_content += "<h2 id='NonWorking'>Non-Working Sites</h2><ul>"
for site_name, url, reason in non_working_sites:
    html_content += f"<li>{site_name} - {url}<br><em>Reason: {reason}</em></li>"
html_content += "</ul>"

html_content += """
    </div>
</body>
</html>
"""

# Save HTML
with open("approved_websites.html", "w", encoding="utf-8") as f:
    f.write(html_content)

print("HTML page generated and saved as 'approved_websites.html'.")
