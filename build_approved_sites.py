import argparse
import base64
import json
import random
import re
import sys
import time
import html

from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup

# Try to use tqdm for a nice progress bar, fall back gracefully if not installed
try:
    from tqdm import tqdm  # type: ignore
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

# ---------------------------------------------------------------------------
# Files (same semantics as old script)
# ---------------------------------------------------------------------------
REPORTS_FILE = "reports/site_reports.json"
CATEGORY_CHANGES_FILE = "reports/category_changes.json"
DESCRIPTIONS_FILE = "reports/site_descriptions.json"

# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------
# Tuned keyword lists based on the current set of approved sites.
# Order matters only when scores tie.
category_keywords = {
    # Programming & web dev (code-focused; design tools are allowed,
    # but 3D creation / Blender is handled under Technology).
    "Programming": [
        # General dev / coding
        "programming", "coding", "code", "developer", "developers",
        "development", "web development", "software development",
        "software engineer", "software engineering",

        # Languages / stacks
        "javascript", "js", "typescript", "python", "java", "c#", "c++",
        "php", "sql", "sqlite", "html", "css",

        # Frameworks / engines / docs
        "react", "create react app", "node", "node.js", "nodejs", "express",
        "api", "apis", "mdn",
        "w3schools", "stack overflow", "stackoverflow", "github", "gitlab",
        "unity", "unity learn", "unreal engine", "epic games",

        # Learning platforms for coding
        "freecodecamp", "codingame", "coderbyte", "unity learn",

        # Web design helpers (still fine to treat as part of the dev toolbox)
        "font", "fonts", "typography", "typeface",
        "color palette", "color palettes", "palette", "palettes",
        "designer", "designers", "web design", "ui", "ux",
        "lorem ipsum", "ipsum",
    ],

    # General education: colleges, textbooks, libraries, curricula, etc.
    "Education": [
        "edu", "school", "schools", "college", "university", "universities",
        "campus", "degree", "diploma", "high school", "k-12", "k12",
        "course", "courses", "curriculum", "class", "classes",
        "career school", "career and technical education",
        "ctc", "cte",

        # Textbooks / content platforms
        "textbook", "textbooks", "online textbook", "online textbooks",
        "openstax", "goodheart-willcox", "g-w learning", "g-w textbooks",
        "vitalsource", "bookshelf",

        # Libraries / reference / research
        "library", "libraries", "catalog", "research database",
        "research databases", "journal", "journals", "encyclopedia",
        "encyclopaedia", "reference", "jstor", "ebsco",

        # Learning platforms / LMS
        "learning portal", "learning platform", "online course",
        "online courses", "study.com", "khan academy", "aztec",
        "gw learning", "penn foster", "life skills reimagined",
        "boardworks", "study skills",

        # Misc higher-ed signals
        "college credit", "accredited", "credit-by-exam",
    ],

    # Government, agencies, official .gov resources
    "Government": [
        "gov", ".gov", "official site", "official website",
        "department of", "federal", "agency",

        # Agencies / programs present in the list
        "usda", "aphis", "fsis", "epa", "environmental protection agency",
        "dea", "diversion control",
        "dol", "department of labor",
        "hhs", "health and human services", "fda",
        "sec", "securities and exchange commission",
        "sba", "small business administration",
        "census", "census bureau", "irs", "internal revenue service",
        "bls", "bureau of labor statistics",
        "employment security department", "esd.wa.gov",
        "washington state noxious weed control board",
        "usda.gov",
    ],

    # Business / career / jobs
    "Business": [
        "business", "commerce", "market", "finance", "management",
        "entrepreneur", "startup", "corporate", "marketing",
        "small business", "register your business",
        "seattle business magazine",

        # Career / job search
        "career", "careers", "job board", "job search", "job board",
        "worksource", "worksourcewa", "resume", "employers", "employment",
        "indeed", "find the job that's right for you",
    ],

    # Science, veterinary, STEM reference
    "Science": [
        "science", "scientific", "research", "laboratory", "lab",
        "biology", "biological", "biotechnology", "physics", "chemistry",
        "math simulations", "stem", "phet",

        # Veterinary / animal science cluster
        "veterinary", "veterinarian", "vet tech", "vet technician",
        "zoological", "zoology", "animal", "feline", "canine",
        "endocrine", "anatomy", "merck veterinary manual",
        "aaha", "aavsb", "aalas", "aaalac", "avma", "avtaa", "azvt", "navta",

        # Biomedical / life science reference
        "ncbi", "national center for biotechnology information",
        "hypurrcat",
    ],

    # Language, writing, rhetoric
    "Language": [
        "dictionary", "thesaurus", "merriam-webster",
        "vocabulary", "grammar", "conjugation",
        "language learning", "learn a language",
        "rosetta stone", "rosettastone",
        "rhetoric", "oratory", "speech", "speeches",
        "writing lab", "purdue owl", "citation", "plagiarism",
    ],

    # Math / quantitative
    "Math": [
        "math", "mathematics", "algebra", "calculus", "geometry",
        "statistics", "equation", "equations", "formula", "graphing",
        "numerical", "quantitative", "quantitative biology",
        "quantitative finance", "phet", "simulations",
        "wolfram|alpha", "wolfram alpha",
        "wamap", "pauls online math notes", "get sum math",
        "prison math project",
    ],

    # Testing & exam prep / placement / certifications
    "Testing": [
        "accuplacer", "placement test", "placement testing",
        "exam", "exams", "test prep", "test preparation",
        "practice test", "practice problems", "sample questions",
        "ged", "pearsonvue", "pearson vue",
        "assessment platform", "testing center", "quizlet",

        # Certification / OSHA-style training
        "certificate", "certification", "certifications",
        "d.o.l. card", "dol card",
        "osha 10", "osha-10",
        "training course", "training program", "training exam",
    ],

    # News, journalism, fact-checking, media literacy
    "News": [
        "news", "breaking news", "latest headlines", "headline",
        "newspaper", "magazine", "press", "editorial", "opinion",
        "op-ed", "journalism", "journalist", "journalists",
        "media literacy", "newsroom", "reporting",

        # Specific orgs in this set
        "ap news", "associated press",
        "el nuevo día", "noticias", "periódico", "periodico",
        "columbia journalism review", "cjr",
        "poynter", "journalist's resource", "journalists resource",
        "prison journalism project",
        "pew research center", "fact tank",
        "politifact", "fact-check", "fact checking",
        "pbs",
        "seattle business magazine",
    ],

    # History & social studies
    "History": [
        "history", "historical", "historical society",
        "social studies", "civil war", "revolutionary war",
        "battlefield", "battlefields", "american battlefield trust",
        "washington state historical society",
        "museum", "museums", "archives",
        "this day in history",
        "model train festival",
    ],

    # Support / help / portals
    "Support": [
        "support", "help center", "help desk", "contact support",
        "knowledge base", "support home", "support home page",
        "customer service", "faq", "frequently asked questions",
        "manuals", "articles to support", "recent updates",

        # Specific portals
        "microsoft support",
        "corrections education reference center",
        "student support", "faculty support",
        "penn foster support", "libapps login",
    ],

    # General technology / tools that are not clearly programming-focused
    "Technology": [
        "tech", "technology", "cloud platform", "cloud service",
        "online platform", "digital platform", "saas",
        "video conferencing", "web conferencing", "webinars",
        "zoom", "zoom rooms",
        "devices", "device", "hardware", "networking",
        "it training", "computer skills", "computer training",

        # 3D / creative tools that are more "software" than "coding"
        "3d software", "3d creation software", "3d creation",
        "blender",
    ],
}


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------
def normalize_url(raw: str) -> str:
    """Normalize URL by adding https:// if no scheme is present."""
    raw = str(raw or "").strip()
    if not raw:
        return ""
    if not raw.lower().startswith(("http://", "https://")):
        raw = "https://" + raw
    parsed = urlparse(raw)
    if not parsed.netloc and parsed.path:
        return "https://" + parsed.path
    return parsed.geturl()


def escape_html(s: str) -> str:
    import html as html_mod
    return html_mod.escape(str(s), quote=False)


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------
def load_reports():
    """Load existing reports from JSON file."""
    try:
        with open(REPORTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []
    except Exception as e:
        print(f"Warning: Could not load reports file: {e}")
        return []


def save_reports(reports):
    """Save reports to JSON file"""
    try:
        Path(REPORTS_FILE).parent.mkdir(parents=True, exist_ok=True)
        with open(REPORTS_FILE, "w", encoding="utf-8") as f:
            json.dump(reports, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Warning: Could not save reports file: {e}")


# ---------------------------------------------------------------------------
# Category changes (admin overrides)
# ---------------------------------------------------------------------------
def load_category_changes():
    """Load admin category changes from JSON file."""
    try:
        with open(CATEGORY_CHANGES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []
    except Exception as e:
        print(f"Warning: Could not load category changes file: {e}")
        return []


def save_category_changes(changes):
    """Save admin category changes to JSON file."""
    try:
        Path(CATEGORY_CHANGES_FILE).parent.mkdir(parents=True, exist_ok=True)
        with open(CATEGORY_CHANGES_FILE, "w", encoding="utf-8") as f:
            json.dump(changes, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Warning: Could not save category changes file: {e}")


def categorize_auto(site_name: str, site_url: str, description: str | None) -> str:
    """
    Automatic categorization using a simple scoring system.

    - Looks at site title, URL, and description.
    - Each keyword match contributes to a category score:
        * URL match:      +3
        * Title match:    +2
        * Description:    +1
    - Returns the category with the highest score, or 'Other' if no matches.
    """
    text_title = (site_name or "").lower()
    text_url = (site_url or "").lower()
    text_desc = (description or "").lower()

    best_category = "Other"
    best_score = 0

    for category, keywords in category_keywords.items():
        score = 0
        for keyword in keywords:
            kw = keyword.lower()
            if kw in text_url:
                score += 3
            if kw in text_title:
                score += 2
            if kw in text_desc:
                score += 1

        if score > best_score:
            best_score = score
            best_category = category

    if best_score == 0:
        return "Other"
    return best_category


def get_category_for_site(
    site_name: str,
    site_url: str,
    description: str,
    category_changes: list,
) -> str:
    """
    Get category for a site, respecting admin overrides first.

    - If there is an applied override for this (site_name, site_url), use it.
    - Otherwise, use automatic categorization based on title, URL, and description.
    """
    for change in category_changes:
        if (
            change.get("site_name") == site_name
            and change.get("site_url") == site_url
            and change.get("status") == "applied"
        ):
            return change.get("new_category", "Other")

    return categorize_auto(site_name, site_url, description)


# ---------------------------------------------------------------------------
# Descriptions (JSON backed + BeautifulSoup scraping)
# ---------------------------------------------------------------------------
def load_descriptions():
    """Load existing site descriptions from JSON file."""
    try:
        with open(DESCRIPTIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"Warning: Could not load descriptions file: {e}")
        return {}


def save_descriptions(descriptions: dict):
    """Save site descriptions to JSON file."""
    try:
        Path(DESCRIPTIONS_FILE).parent.mkdir(parents=True, exist_ok=True)
        with open(DESCRIPTIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(descriptions, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Warning: Could not save descriptions file: {e}")


def analyze_website(url: str, site_name: str) -> dict:
    """
    Analyze a website and generate a description.

    - Fetch HTML with a browser-like User-Agent
    - Try <title>, meta[name=description], og:description, twitter:description
    - Then headings + paragraphs for fallback summary
    """
    try:
        time.sleep(random.uniform(1, 3))

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

        resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "")
        if "text/html" not in content_type:
            domain = urlparse(url).netloc
            return {
                "description": f"Educational resource ({domain})",
                "title": site_name,
                "meta_description": "",
                "status": "non-html",
                "timestamp": datetime.now().isoformat(),
            }

        soup = BeautifulSoup(resp.text, "html.parser")

        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()

        meta_description = ""
        meta = soup.find("meta", attrs={"name": "description"})
        if meta:
            raw = (meta.get("content") or "").strip()
            meta_description = html.unescape(raw)

        if not meta_description:
            og_desc = soup.find("meta", attrs={"property": "og:description"})
            if og_desc:
                raw = (og_desc.get("content") or "").strip()
                meta_description = html.unescape(raw)

        if not meta_description:
            twitter_desc = soup.find("meta", attrs={"name": "twitter:description"})
            if twitter_desc:
                raw = (twitter_desc.get("content") or "").strip()
                meta_description = html.unescape(raw)

        content_elements: list[str] = []

        main_content = (
            soup.find("main")
            or soup.find("article")
            or soup.find("section")
        )

        if not main_content:
            for selector in [
                "div.content",
                "div.main-content",
                "div.page-content",
                "div#content",
                "div#main",
            ]:
                main_content = soup.select_one(selector)
                if main_content:
                    break

        if not main_content:
            main_content = soup.find("body")

        skip_tokens = ["cookie", "privacy", "terms", "navigation", "menu", "footer"]

        if main_content:
            headings = main_content.find_all(["h1", "h2", "h3", "h4"])
            for h in headings[:5]:
                raw = re.sub(r"\s+", " ", h.get_text().strip())
                txt = html.unescape(raw)
                if txt and 10 < len(txt) < 250:
                    content_elements.append(txt)

            paragraphs = main_content.find_all("p")
            for p in paragraphs[:5]:
                raw = re.sub(r"\s+", " ", p.get_text().strip())
                txt = html.unescape(raw)
                if (
                    txt
                    and 30 < len(txt) < 500
                    and not any(t in txt.lower() for t in skip_tokens)
                ):
                    content_elements.append(txt)

        domain = urlparse(url).netloc
        if meta_description:
            description = meta_description
        elif content_elements:
            description = " ".join(content_elements)
        elif site_name and len(site_name) > 3:
            description = f"{site_name} – Educational resource ({domain})"
        else:
            description = f"Educational resource ({domain})"

        return {
            "description": description,
            "title": title or site_name,
            "meta_description": meta_description,
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
        }

    except requests.exceptions.RequestException:
        domain = urlparse(url).netloc
        if site_name and len(site_name) > 3:
            fallback = f"{site_name} – Educational resource ({domain})"
        else:
            fallback = f"Educational resource ({domain})"
        return {
            "description": fallback,
            "title": site_name,
            "meta_description": "",
            "status": "error",
            "timestamp": datetime.now().isoformat(),
        }


def pick_description_for_site(
    site_name: str,
    url: str,
    row_desc: str | None,
    descriptions_map: dict,
    generate_missing: bool,
    force_regen: bool,
) -> str:
    """
    Decide which description to use / generate for a given site.
    - If force_regen: always re-scrape.
    - Else if URL already in descriptions_map: use cached.
    - Else if generate_missing: scrape and store.
    - Else: fall back to CSV description or generic fallback.
    """
    key = url

    if force_regen:
        info = analyze_website(url, site_name)
        descriptions_map[key] = info
        return info["description"]

    if key in descriptions_map and "description" in descriptions_map[key]:
        return descriptions_map[key]["description"]

    if generate_missing:
        info = analyze_website(url, site_name)
        descriptions_map[key] = info
        return info["description"]

    if row_desc and row_desc.strip():
        return row_desc.strip()

    domain = urlparse(url).netloc
    if site_name and len(site_name) > 3:
        return f"{site_name} – Educational resource ({domain})"
    return f"Educational resource ({domain})"


# ---------------------------------------------------------------------------
# Favicon fetching
# ---------------------------------------------------------------------------
class FaviconFetcher:
    def __init__(self, enabled: bool):
        self.enabled = enabled
        self.cache: dict[str, str] = {}

    def _fetch_google(self, domain: str) -> str | None:
        """Try Google S2 favicon service first."""
        url = f"https://www.google.com/s2/favicons?sz=32&domain_url={domain}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        mime = resp.headers.get("Content-Type", "image/png")
        b64 = base64.b64encode(resp.content).decode("ascii")
        return f"data:{mime};base64,{b64}"

    def _fetch_from_html(self, url: str) -> str | None:
        """
        Fallback: download the page, parse <link rel="icon" ...>, and fetch that.
        Handles cases like Evergreen's /themes/.../favicon.ico.
        """
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            )
        }

        # Get the page
        resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Look for common icon rel values
        icon_link = None

        def is_icon_link(tag):
            if tag.name != "link":
                return False
            rel = tag.get("rel") or []
            # rel can be list or string; normalize to lower-case string
            rel_str = " ".join(rel).lower() if isinstance(rel, (list, tuple)) else str(rel).lower()
            return any(key in rel_str for key in ["icon", "shortcut icon", "apple-touch-icon"])

        for link in soup.find_all(is_icon_link):
            icon_link = link
            break

        if not icon_link:
            return None

        href = icon_link.get("href")
        if not href:
            return None

        # Make URL absolute
        icon_url = urljoin(resp.url, href)

        # Fetch the icon
        icon_resp = requests.get(icon_url, timeout=15)
        icon_resp.raise_for_status()

        mime = icon_resp.headers.get("Content-Type", "image/x-icon")
        b64 = base64.b64encode(icon_resp.content).decode("ascii")
        return f"data:{mime};base64,{b64}"

    def for_url(self, url: str) -> str:
        """
        Get a favicon data: URL for a site, with caching:
        - Try Google S2.
        - If that fails, try parsing the page HTML for <link rel="icon" ...>.
        """
        if not self.enabled:
            return ""

        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path
        domain = domain.lower()

        if not domain:
            return ""

        if domain in self.cache:
            return self.cache[domain]

        data_url = None

        # 1) Try Google S2
        try:
            data_url = self._fetch_google(domain)
        except Exception:
            data_url = None

        # 2) Fallback: parse HTML for <link rel="icon"...>
        if not data_url:
            try:
                data_url = self._fetch_from_html(url)
            except Exception:
                data_url = None

        self.cache[domain] = data_url or ""
        return self.cache[domain]


# ---------------------------------------------------------------------------
# HTML fragment builders
# ---------------------------------------------------------------------------
def build_nav_html(categorized: dict[str, list]) -> str:
    cats = sorted(categorized.keys())
    parts: list[str] = []
    for cat in cats:
        count = len(categorized[cat])
        safe = escape_html(cat)
        parts.append(
            f'''            <li class="category-item">
              <a href="#{safe}" class="category-link" onclick="scrollToCategory('{safe}'); return false;">
                <span class="category-name">{safe}</span>
                <span class="category-count">{count}</span>
              </a>
            </li>'''
        )
    return "\n".join(parts)


def build_sections_html(categorized: dict[str, list], favicons: FaviconFetcher) -> str:
    cats = sorted(categorized.keys())
    sections: list[str] = []

    for cat in cats:
        safe_cat = escape_html(cat)
        site_items: list[str] = []

        for name, url, desc in categorized[cat]:
            fav_src = favicons.for_url(url)
            img_attrs = 'class="site-favicon" alt="" aria-hidden="true"'
            if fav_src:
                img_html = f'<img {img_attrs} src="{escape_html(fav_src)}">'
            else:
                img_html = f'<img {img_attrs}>'

            site_items.append(
                f"""            <li class="site-item">
              {img_html}
              <div class="site-name">{escape_html(name)}</div>
              <div class="site-url">{escape_html(url)}</div>
              <div class="site-description">{escape_html(desc)}</div>
              <div class="site-actions">
                <a href="{escape_html(url)}" target="_blank" class="visit-btn">Visit Site</a>
              </div>
            </li>"""
            )

        section_html = f"""        <div id="{safe_cat}" class="category-section">
          <h2 class="category-title">{safe_cat}</h2>
          <ul class="site-list">
{chr(10).join(site_items)}
          </ul>
        </div>"""
        sections.append(section_html)

    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------
def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Build approved websites HTML from SharePoint CSV + template, with descriptions, category overrides, reports, and favicons."
    )
    parser.add_argument("csv", help="SharePoint_List_Export_*.csv")
    parser.add_argument(
        "-t",
        "--template",
        default="template.html",
        help="HTML template file (default: template.html)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="index.html",
        help="Output HTML file (default: index.html)",
    )

    # Description behavior: default = do everything (regen all).
    desc_group = parser.add_mutually_exclusive_group()
    desc_group.add_argument(
        "--no-descriptions",
        action="store_true",
        help="Disable scraping: do not fetch any descriptions (use JSON/CSV/fallback only).",
    )
    desc_group.add_argument(
        "--descriptions-missing-only",
        action="store_true",
        help="Only scrape descriptions for sites missing in the JSON (no regen of existing).",
    )

    # Favicons: default = embed favicons.
    parser.add_argument(
        "--no-embed-favicons",
        action="store_true",
        help="Disable favicon fetching (no data: URLs).",
    )

    args = parser.parse_args(argv)

    template_path = Path(args.template)
    if not template_path.exists():
        raise SystemExit(f"Template not found: {template_path}")

    df = pd.read_csv(args.csv)

    if "Title" not in df.columns or "Website_Url" not in df.columns:
        raise SystemExit("CSV must contain at least 'Title' and 'Website_Url' columns.")

    if not HAS_TQDM:
        print("Note: tqdm is not installed. Run 'pip install tqdm' to get a fancy progress bar.")
        print("Proceeding with simple progress output.\n")

    descriptions = load_descriptions()
    reports = load_reports()
    category_changes = load_category_changes()

    # Default: do everything
    force_regen = True
    generate_missing = True

    # If user disables or restricts descriptions:
    if args.no_descriptions:
        force_regen = False
        generate_missing = False
    elif args.descriptions_missing_only:
        force_regen = False
        generate_missing = True

    # Favicons: default embed, unless explicitly disabled
    embed_favicons = not args.no_embed_favicons

    categorized: dict[str, list] = defaultdict(list)
    total_rows = len(df)
    has_desc_col = "Website_Description" in df.columns

    # Some simple counters for summary
    scraped_count = 0
    cached_count = 0
    disabled_count = 0

    # Build iterator with or without tqdm
    if HAS_TQDM:
        iterator = enumerate(
            tqdm(
                df.itertuples(index=False),
                total=total_rows,
                desc="Processing sites",
                unit="site",
            ),
            start=1,
        )
    else:
        iterator = enumerate(df.itertuples(index=False), start=1)

    for idx, row in iterator:
        name = str(row.Title).strip()
        raw_url = str(row.Website_Url).strip()

        if not name or not raw_url:
            if HAS_TQDM:
                tqdm.write(f"[{idx}/{total_rows}] Skipping empty row")
            else:
                print(f"[{idx}/{total_rows}] Skipping empty row")
            continue

        if "removed" in name.lower() or "removed" in raw_url.lower():
            if HAS_TQDM:
                tqdm.write(f"[{idx}/{total_rows}] Skipping removed site: {name}")
            else:
                print(f"[{idx}/{total_rows}] Skipping removed site: {name}")
            continue

        url = normalize_url(raw_url)
        row_desc = ""
        if has_desc_col:
            row_desc = str(getattr(row, "Website_Description", "") or "")

        # Decide description mode for logging/counters
        if args.no_descriptions:
            desc_mode = "disabled"
            disabled_count += 1
        elif args.descriptions_missing_only and url in descriptions:
            desc_mode = "cached"
            cached_count += 1
        else:
            desc_mode = "scrape"
            scraped_count += 1

        msg_prefix = f"[{idx}/{total_rows}]"
        if desc_mode == "disabled":
            msg = f"{msg_prefix} Descriptions disabled: {name}"
        elif desc_mode == "cached":
            msg = f"{msg_prefix} Using cached description: {name}"
        else:
            msg = f"{msg_prefix} Scraping description: {name}"

        if HAS_TQDM:
            tqdm.write(msg)
        else:
            print(msg)

        desc = pick_description_for_site(
            site_name=name,
            url=url,
            row_desc=row_desc,
            descriptions_map=descriptions,
            generate_missing=generate_missing,
            force_regen=force_regen,
        )

        # Use description-aware categorization (with admin overrides)
        category = get_category_for_site(name, url, desc, category_changes)

        if embed_favicons:
            # We do not fetch here (that happens in build_sections_html),
            # but this makes it clear that favicon embedding is enabled.
            if HAS_TQDM:
                tqdm.write(f"{msg_prefix} (Favicons enabled) {name}")
            else:
                print(f"{msg_prefix} (Favicons enabled) {name}")

        categorized[category].append((name, url, desc))

    # Persist JSON sidecars
    save_descriptions(descriptions)
    save_reports(reports)
    save_category_changes(category_changes)

    for cat in categorized:
        categorized[cat].sort(key=lambda t: t[0].lower())

    total_sites = sum(len(v) for v in categorized.values())
    total_categories = len(categorized)
    last_updated = datetime.now().strftime("%Y-%m-%d %H:%M")

    nav_html = build_nav_html(categorized)
    sections_html = build_sections_html(categorized, FaviconFetcher(embed_favicons))

    template = template_path.read_text(encoding="utf-8")

    for placeholder in [
        "{{CATEGORY_NAV}}",
        "{{CATEGORY_SECTIONS}}",
        "{{TOTAL_SITES}}",
        "{{TOTAL_CATEGORIES}}",
        "{{LAST_UPDATED}}",
    ]:
        if placeholder not in template:
            print(f"Warning: placeholder {placeholder} not found in template.")

    html_out = (
        template.replace("{{CATEGORY_NAV}}", nav_html)
        .replace("{{CATEGORY_SECTIONS}}", sections_html)
        .replace("{{TOTAL_SITES}}", str(total_sites))
        .replace("{{TOTAL_CATEGORIES}}", str(total_categories))
        .replace("{{LAST_UPDATED}}", last_updated)
    )

    Path(args.output).write_text(html_out, encoding="utf-8")

    print()
    print(f"Wrote {args.output} with {total_sites} sites across {total_categories} categories.")
    if args.no_descriptions:
        print("Descriptions: scraping DISABLED (using existing JSON/CSV/fallback).")
    elif args.descriptions_missing_only:
        print("Descriptions: scraped ONLY for sites missing in JSON (existing cached kept).")
    else:
        print("Descriptions: regenerated for ALL sites (default).")

    print(f"Description summary: scraped={scraped_count}, cached={cached_count}, disabled={disabled_count}")

    if embed_favicons:
        print("Favicons: embedded as data: URLs (default).")
    else:
        print("Favicons: fetching DISABLED.")


if __name__ == "__main__":
    main()
