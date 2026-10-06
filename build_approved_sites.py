import argparse
import base64
import csv
import json
import os
import random
import re
import socket
import sys
import time
import html

from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urljoin, urlunparse

import requests
from bs4 import BeautifulSoup

import history
import history_backfill
import trend_report
from urlkeys import normalize_url, url_key

# Try to use tqdm for a nice progress bar, fall back gracefully if not installed
try:
    from tqdm import tqdm  # type: ignore
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------
CSV_DIR = "site_extracts"
CATEGORY_CHANGES_FILE = "data/category_changes.json"
DESCRIPTIONS_FILE = "data/site_descriptions.json"
URL_OVERRIDES_FILE = "data/url_overrides.json"
URL_SUGGESTIONS_FILE = "data/url_overrides.suggested.json"
EXCLUDED_SITES_FILE = "data/excluded_sites.json"

# --check-links writes a timestamped report here on every run, in both formats,
# so there is always something to send on and a history to compare against.
LINK_REPORT_DIR = "link_reports"

# Columns the CSV must provide. DOC exports name the URL column "Website";
# "Website_Url" is accepted too, for exports that were converted by hand
# before the builder understood the DOC default.
TITLE_COLUMN = "Title"
URL_COLUMNS = ("Website", "Website_Url")

# DOC exports tag each row with the whitelists it belongs to, e.g.
# ["IncarEducation"] or ["IncarEducation","IncarVetProgramWhitelist"].
# This page covers education only, so rows are kept when their categories
# mention CATEGORY_FILTER. Substring matching is deliberate: it also picks up
# IncarEducationStudent and IncarEducationStaffURL. Exports without the column
# are used in full.
CATEGORY_COLUMN = "URL Category"
CATEGORY_FILTER = "IncarEducation"

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
        # "edu" used to match inside "education" and "educational" as a
        # substring; whole-word matching needs the words themselves.
        "edu", "education", "educational", "educator", "educators",
        "school", "schools", "college", "university", "universities",
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
        # As with "edu": "gov" was standing in for "government" by matching
        # inside it.
        "gov", "government", "governmental", ".gov",
        "official site", "official website",
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
        # Named like the other site-specific entries here: these domains run
        # the words together, so no word boundary exists for "math" to match.
        "wamap", "openmath", "myopenmath",
        "pauls online math notes", "get sum math",
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
def looks_like_url(raw: str) -> bool:
    """
    Whether a CSV cell is an address rather than a note someone typed in the
    URL column.

    DOC exports carry rows whose URL field is a sentence — "Link is in place
    for mandatory entry... it is not a valid website.", "Open Website sort and
    filter menu". Without this they were normalized into https://Link%20is...,
    put on the page as live links, and scraped, which is how four entries keyed
    by prose ended up in the description cache.

    Deliberately loose: the job is to reject prose, not to validate hostnames.
    """
    raw = str(raw or "").strip()
    if not raw or any(c.isspace() for c in raw):
        return False
    host = urlparse(normalize_url(raw)).netloc
    return "." in host and not host.startswith(".") and not host.endswith(".")


def escape_html(s: str) -> str:
    """
    Escape a value for HTML, quotes included.

    Quotes matter because this output goes into attributes as well as text —
    href, src, the favicon data: URL — where an unescaped double quote closes
    the attribute early and the rest of the tag becomes markup. In a text node
    the escaped form renders identically, so one helper covers both safely.
    """
    return html.escape(str(s), quote=True)


def write_text_atomic(path: Path, text: str, encoding: str = "utf-8") -> None:
    """
    Write a file by replacing it in one step, rather than truncating it first.

    Two of the files this script writes are expensive to lose. The description
    cache is roughly an hour of scraping, and the default build rewrites it
    wholesale; the generated page is what students actually open. Writing in
    place means a Ctrl-C, a full disk or a crash lands between the truncate and
    the rewrite, leaving a half-written file where a good one used to be.

    Writing to a temporary file in the same directory and renaming it over the
    original avoids that: os.replace is atomic on a single filesystem, so the
    old file survives intact until the new one is complete.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        with open(tmp, "w", encoding=encoding, newline="") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------------------
# URL overrides
# ---------------------------------------------------------------------------
def load_url_overrides() -> tuple[dict, dict]:
    """
    Load URL corrections, keyed for matching. Returns (replace, remove).

    DOC exports carry URLs that don't load as written — a missing www, a host
    that moved, a site that has since expired. Fixing them here rather than in
    the generated page means the corrections survive the next export.
    """
    try:
        with open(URL_OVERRIDES_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        return {}, {}
    except Exception as e:
        print(f"Warning: Could not load URL overrides file: {e}")
        return {}, {}

    replace = {}
    for k, v in (raw.get("replace") or {}).items():
        target = v.get("url") if isinstance(v, dict) else v
        if target:
            replace[url_key(k)] = target

    remove = {url_key(k): v for k, v in (raw.get("remove") or {}).items()}
    return replace, remove


# ---------------------------------------------------------------------------
# Excluded sites
# ---------------------------------------------------------------------------
def load_excluded_sites() -> dict[str, str]:
    """
    Load the sites kept off the page whatever DOC approves, keyed for matching.

    Kept apart from the overrides' remove block on purpose. That block fixes
    broken links and matches one exact address; this is a policy decision, so
    it matches a whole host — DOC re-listing a site under a different path or
    subdomain must not bring it back.

    A file that exists but can't be read stops the build rather than warning:
    carrying on would publish exactly the sites this file exists to withhold.
    """
    try:
        with open(EXCLUDED_SITES_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        raise SystemExit(
            f"Could not read {EXCLUDED_SITES_FILE}: {e}\n"
            f"Fix the file before building, so excluded sites stay off the page."
        )

    return {
        url_key(k): str(v or "")
        for k, v in (raw.get("exclude") or {}).items()
        if url_key(k)
    }


def excluded_by(url: str, excluded: dict[str, str]) -> str | None:
    """
    The exclusion entry that covers url, or None.

    An entry with no path covers its host and every subdomain of it; one with a
    path covers that path and everything beneath it on the same host.
    """
    key = url_key(url)
    host, _, path = key.partition("/")
    for entry in excluded:
        e_host, _, e_path = entry.partition("/")
        if host != e_host and not host.endswith("." + e_host):
            continue
        if not e_path:
            return entry
        if host == e_host and (path == e_path or path.startswith(e_path + "/")):
            return entry
    return None


# ---------------------------------------------------------------------------
# Category changes (manual overrides)
# ---------------------------------------------------------------------------
def load_category_changes():
    """Load manual category overrides from JSON file."""
    try:
        with open(CATEGORY_CHANGES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []
    except Exception as e:
        print(f"Warning: Could not load category changes file: {e}")
        return []


# Keywords are matched as whole words rather than as bare substrings. Plain
# one-word keywords are checked against the text's tokens; anything carrying
# punctuation or a space ("node.js", "c++", "k-12", "stack overflow") is
# matched as a literal substring, because splitting it into tokens would throw
# away exactly what makes it distinctive.
_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Endings stripped to give each token a stem, so "courses" still matches the
# keyword "course" and "supporting" still matches "support". Substring matching
# used to get this for free, along with every false positive below it; matching
# the stem keeps the plurals without letting "lab" match "available".
_SUFFIXES = ("es", "s", "ed", "ing", "al", "ic")


def _tokens(text: str) -> set[str]:
    """Every word in the text, plus a stem for each so inflections still match."""
    words = _TOKEN_RE.findall(text)
    out = set(words)
    for word in words:
        for suffix in _SUFFIXES:
            if word.endswith(suffix) and len(word) - len(suffix) >= 3:
                out.add(word[: -len(suffix)])
    return out


def categorize_auto(site_name: str, site_url: str, description: str | None) -> str:
    """
    Automatic categorization using a simple scoring system.

    - Looks at site title, URL, and description.
    - Each keyword match contributes to a category score:
        * URL match:      +3
        * Title match:    +2
        * Description:    +1
    - Returns the category with the highest score, or 'Other' if no matches.

    Matching is on whole words. Plain substring matching put short keywords
    inside unrelated longer ones — "js" inside jstor.org, "lab" inside
    collaborate, "api" inside capital, "sec" inside second — which filed sites
    under categories nothing in them supported. Whole words also mean a keyword
    can be added without first checking that it does not happen to be a
    fragment of some other word.
    """
    text_title = (site_name or "").lower()
    text_url = (site_url or "").lower()
    text_desc = (description or "").lower()

    tokens_title = _tokens(text_title)
    tokens_url = _tokens(text_url)
    tokens_desc = _tokens(text_desc)

    best_category = "Other"
    best_score = 0

    for category, keywords in category_keywords.items():
        score = 0
        for keyword in keywords:
            kw = keyword.lower()
            if _TOKEN_RE.fullmatch(kw):
                in_url, in_title, in_desc = (
                    kw in tokens_url, kw in tokens_title, kw in tokens_desc,
                )
            else:
                in_url, in_title, in_desc = (
                    kw in text_url, kw in text_title, kw in text_desc,
                )

            if in_url:
                score += 3
            if in_title:
                score += 2
            if in_desc:
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
    Get category for a site, respecting manual overrides first.

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
    """Save site descriptions to JSON file, replacing it in one step."""
    try:
        write_text_atomic(
            Path(DESCRIPTIONS_FILE),
            json.dumps(descriptions, indent=2, ensure_ascii=False),
        )
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


def description_mode(
    url: str,
    descriptions_map: dict,
    generate_missing: bool,
    force_regen: bool,
) -> str:
    """
    Where this site's description will come from: "scrape", "cached" or "fallback".

    The build announces and counts the mode before doing the work, and
    pick_description_for_site then does it. Both ask this function, so the line
    the build prints cannot disagree with what it then does. They used to: the
    loop tested only whether the URL was a key in the cache, while the picker
    also required a description inside that entry, so an entry missing one was
    announced as "Using cached description" and then scraped.
    """
    if force_regen:
        return "scrape"

    cached = descriptions_map.get(url)
    if isinstance(cached, dict) and cached.get("description"):
        return "cached"

    return "scrape" if generate_missing else "fallback"


def pick_description_for_site(
    site_name: str,
    url: str,
    row_desc: str | None,
    descriptions_map: dict,
    generate_missing: bool,
    force_regen: bool,
) -> str:
    """
    Get the description for a site, scraping it if that is the chosen mode.
    Falls back to the CSV's own description, then to a generic line.
    """
    mode = description_mode(url, descriptions_map, generate_missing, force_regen)

    if mode == "scrape":
        info = analyze_website(url, site_name)
        descriptions_map[url] = info
        return info["description"]

    if mode == "cached":
        return descriptions_map[url]["description"]

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
        return self._image_data_url(
            resp.content, resp.headers.get("Content-Type", "image/png")
        )

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
        return self._image_data_url(
            icon_resp.content, icon_resp.headers.get("Content-Type", "image/x-icon")
        )

    @staticmethod
    def _image_data_url(content: bytes, header_mime: str) -> str | None:
        """
        Build an image data: URL, trusting the bytes over the Content-Type.

        Some servers label a .ico as text/plain or application/octet-stream,
        and a browser will not render <img src="data:text/plain;...">, so the
        icon would silently come out blank. Sniff the signature instead and
        fall back to the header only when it already claims an image.
        """
        if not content:
            return None

        sniffed = None
        if content.startswith(b"\x00\x00\x01\x00"):
            sniffed = "image/x-icon"
        elif content.startswith(b"\x89PNG\r\n\x1a\n"):
            sniffed = "image/png"
        elif content.startswith(b"GIF8"):
            sniffed = "image/gif"
        elif content.startswith(b"\xff\xd8\xff"):
            sniffed = "image/jpeg"
        elif content[:4] == b"RIFF" and content[8:12] == b"WEBP":
            sniffed = "image/webp"
        elif content.lstrip()[:4].lower() in (b"<svg", b"<?xm"):
            sniffed = "image/svg+xml"

        mime = sniffed or header_mime.split(";")[0].strip()
        if not mime.startswith("image/"):
            return None

        b64 = base64.b64encode(content).decode("ascii")
        return f"data:{mime};base64,{b64}"

    def _fetch_default_path(self, parsed) -> str | None:
        """
        Last resort: /favicon.ico on the site's own scheme and host.

        Deliberately not redirect-following to a different host — a site that
        404s its bare domain onto www (or onto a parked page) would otherwise
        hand back that host's icon, or an HTML error page dressed as one.
        """
        scheme = parsed.scheme or "https"
        origin = f"{scheme}://{parsed.netloc}"
        resp = requests.get(f"{origin}/favicon.ico", timeout=10)
        resp.raise_for_status()
        return self._image_data_url(
            resp.content, resp.headers.get("Content-Type", "image/x-icon")
        )

    def for_url(self, url: str) -> str:
        """
        Get a favicon data: URL for a site, with caching:
        - Try Google S2, once more after a pause if it fails. Over a hundred
          sites in quick succession, S2 intermittently refuses a request that
          succeeds on its own; without the retry one blip drops an icon that
          is perfectly fetchable.
        - Then parse the page HTML for <link rel="icon" ...>.
        - Then try /favicon.ico at the site's own origin, which covers sites
          that declare no icon link and that S2 has no record of.
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

        # 1) Try Google S2, with one retry
        for attempt in range(2):
            try:
                data_url = self._fetch_google(domain)
                break
            except Exception:
                data_url = None
                if attempt == 0:
                    time.sleep(1.5)

        # 2) Fallback: parse HTML for <link rel="icon"...>
        if not data_url:
            try:
                data_url = self._fetch_from_html(url)
            except Exception:
                data_url = None

        # 3) Fallback: the conventional /favicon.ico on the site's own origin
        if not data_url:
            try:
                data_url = self._fetch_default_path(parsed)
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
              <a href="#{safe}" class="category-link" onclick="scrollToCategory(this.hash.slice(1)); return false;">
                <span class="category-name">{safe}</span>
                <span class="category-count">{count}</span>
              </a>
            </li>'''
        )
    return "\n".join(parts)


def build_sections_html(categorized: dict[str, list], favicons: FaviconFetcher) -> str:
    cats = sorted(categorized.keys())
    sections: list[str] = []

    # Fetching the icons is the slow part of this function — up to three
    # network requests per site — so it reports progress. The build loop used
    # to print a line per site saying favicons were enabled, which described a
    # flag rather than any work, while the work itself happened here in
    # silence.
    total = sum(len(v) for v in categorized.values())
    if favicons.enabled and total:
        print(f"\nFetching favicons for {total} site(s)...")
    done = 0

    for cat in cats:
        safe_cat = escape_html(cat)
        site_items: list[str] = []

        for name, url, desc in categorized[cat]:
            fav_src = favicons.for_url(url)
            if favicons.enabled:
                done += 1
                msg = f"[{done}/{total}] {'icon' if fav_src else 'no icon'}: {name}"
                tqdm.write(msg) if HAS_TQDM else print(msg)
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
# Link checking
# ---------------------------------------------------------------------------
CHECK_WORKERS = 8
CHECK_TIMEOUT = 12
# The serial re-check is deliberately more patient than the concurrent pass:
# a slow site starved of bandwidth by eight parallel requests is not a broken
# one, and reporting it as dead sends someone chasing a site that works.
CHECK_TIMEOUT_RETRY = 30
# Let rate limits from the concurrent pass expire before the serial re-check.
CHECK_COOLDOWN = 8
CHECK_RETRY_SPACING = 1.5

# A 200 is not proof of life: expired and parked domains serve a real page.
PARKING_SIGNATURES = (
    "website expired",
    "this domain has expired",
    "domain has expired",
    "domain is for sale",
    "buy this domain",
    "parked free",
    "domain parking",
    "account suspended",
    "this site is temporarily unavailable",
    "future home of something quite cool",
)

# Statuses that mean "the host is up and answered, but refused an automated
# request". A 403 from a CDN or a 401 from a login portal says nothing about
# whether the site works for a student in a browser, so these are reported
# apart from genuine breakage rather than counted as failures.
BLOCKED_STATUSES = {401, 403, 407, 429, 451}

# Ordered worst-first, which is also the order the report prints them.
CHECK_CLASSES = (
    ("dead_dns", "DEAD — host has no address record"),
    ("parked", "EXPIRED / PARKED — serves a placeholder page"),
    ("unreachable", "UNREACHABLE — no variant responded"),
    ("server_error", "SERVER ERROR — 5xx"),
    ("client_error", "NOT FOUND — 4xx"),
    ("needs_www", "NEEDS www — bare host fails, www works"),
    ("drop_www", "DROP www — www fails, bare host works"),
    ("http_only", "NO HTTPS — only reachable over http"),
    ("moved", "REDIRECTS OFF-HOST — lands on a host that may need whitelisting"),
    ("blocked", "BLOCKED TO AUTOMATION — host is up; verify these by hand"),
    ("ok", "OK"),
)

# Classes that mean a student would hit a broken link.
CHECK_BROKEN = {
    "dead_dns", "parked", "unreachable", "server_error",
    "client_error", "needs_www", "drop_www", "http_only",
}


def host_resolves(host: str) -> bool:
    try:
        socket.getaddrinfo(host, None)
        return True
    except OSError:
        return False


def swap_www(url: str) -> str:
    """The other spelling of a host: www.x.com <-> x.com."""
    p = urlparse(url)
    host = p.netloc
    alt = host[4:] if host.lower().startswith("www.") else "www." + host
    return urlunparse(p._replace(netloc=alt))


def probe(url: str, timeout: int = CHECK_TIMEOUT) -> dict:
    """
    One request. Reports transport failure, status, where it landed, and
    whether the page looks like a parking or expiry placeholder.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    try:
        resp = requests.get(
            url, headers=headers, timeout=timeout, allow_redirects=True
        )
    except requests.RequestException as e:
        return {"error": type(e).__name__, "status": None, "final": None, "parked": False}

    parked = False
    if "html" in resp.headers.get("Content-Type", "").lower():
        head = resp.text[:4000].lower()
        parked = any(sig in head for sig in PARKING_SIGNATURES)

    return {
        "error": None,
        "status": resp.status_code,
        "final": resp.url,
        "parked": parked,
    }


def _alive(p: dict) -> bool:
    return p["error"] is None and p["status"] is not None and p["status"] < 400 and not p["parked"]


def check_site(name: str, url: str, timeout: int = CHECK_TIMEOUT) -> dict:
    """
    Classify one site, trying the listed URL first and then the obvious
    variants so a failure can be reported as a specific, fixable cause
    ("needs www") rather than a bare "broken".
    """
    result = {
        "name": name, "url": url, "klass": "ok", "detail": "",
        "suggest": None, "final": None, "dupe_of": "",
    }
    p = urlparse(url)
    host = p.netloc

    if not host_resolves(host) and not host_resolves(urlparse(swap_www(url)).netloc):
        result.update(klass="dead_dns", detail="no DNS record for host or its www/bare twin")
        return result

    primary = probe(url, timeout)

    result["final"] = primary["final"]

    if _alive(primary):
        final_host = urlparse(primary["final"]).netloc.lower()
        if url_key(final_host) != url_key(host):
            result.update(
                klass="moved",
                detail=f"redirects to {final_host}",
                suggest=primary["final"],
            )
        else:
            result.update(detail=f"HTTP {primary['status']}")
        return result

    if primary["parked"]:
        result.update(klass="parked", detail="placeholder page (expired or parked domain)")
        return result

    # Any HTTP response means the listed URL reached a server, so the URL
    # itself is not malformed. Only a transport failure (no DNS, refused
    # connection, timeout) or a genuine 404 justifies trying www/http variants
    # and concluding the link is written wrong.
    #
    # Skipping this check produced three separate false positives: a 403 from
    # pewresearch.org and a transient Cloudflare 520 from census.gov were both
    # "explained" as a missing www, because a variant happened to answer 200.
    # Both sites work fine as listed.
    if primary["status"] in BLOCKED_STATUSES:
        result.update(
            klass="blocked",
            detail=f"HTTP {primary['status']} — host answered but refused an automated request",
        )
        return result

    if primary["status"] and primary["status"] >= 500:
        result.update(
            klass="server_error",
            detail=f"HTTP {primary['status']} — host answered with a server error",
        )
        return result

    if primary["status"] and primary["status"] not in (404, 410):
        result.update(
            klass="client_error",
            detail=f"HTTP {primary['status']}",
        )
        return result

    # No response at all, or a 404. Now a variant genuinely may explain it.
    www_swapped = swap_www(url)
    https_to_http = urlunparse(p._replace(scheme="http")) if p.scheme == "https" else None
    http_and_swap = urlunparse(urlparse(www_swapped)._replace(scheme="http")) if p.scheme == "https" else None

    bare_is_listed = not host.lower().startswith("www.")
    candidates = [
        ("needs_www" if bare_is_listed else "drop_www", www_swapped),
        ("http_only", https_to_http),
        ("http_only", http_and_swap),
    ]

    for klass, candidate in candidates:
        if not candidate:
            continue
        alt = probe(candidate, timeout)
        if _alive(alt):
            result.update(
                klass=klass,
                detail=f"listed URL failed ({primary['error'] or 'HTTP ' + str(primary['status'])}), "
                       f"{candidate} returns {alt['status']}",
                suggest=alt["final"] or candidate,
            )
            return result

    # Nothing worked. Only two states can reach this point: the checks above
    # have already returned for a blocked status, a 5xx and every 4xx other
    # than 404 and 410, so the listed URL either answered 404/410 or did not
    # answer at all.
    if primary["status"]:
        result.update(
            klass="client_error",
            detail=f"HTTP {primary['status']} on every variant",
        )
    else:
        result.update(klass="unreachable", detail=f"{primary['error']} on every variant")
    return result


def run_link_check(sites: list) -> list[dict]:
    """
    Check every site concurrently, then re-check anything that failed, one at
    a time. Concurrency makes a site look dead when it is merely rate-limiting
    or slow under load, and a serial second opinion costs little when the
    failures are a handful.
    """
    from concurrent.futures import ThreadPoolExecutor

    print(f"\nChecking {len(sites)} links ({CHECK_WORKERS} at a time)...\n")
    with ThreadPoolExecutor(max_workers=CHECK_WORKERS) as pool:
        results = list(pool.map(lambda s: check_site(s[0], s[1]), sites))

    suspect = [r for r in results if r["klass"] in CHECK_BROKEN]
    if suspect:
        # Pause before re-checking, and space the retries out. Without the
        # cooldown the second opinion lands while a rate-limited host is still
        # rate-limiting, and simply confirms the first wrong answer -- which is
        # how a healthy site (pewresearch.org) was reported as needing www.
        print(
            f"Re-checking {len(suspect)} problem link(s) one at a time, "
            f"{CHECK_TIMEOUT_RETRY}s timeout, after a {CHECK_COOLDOWN}s cooldown...\n"
        )
        time.sleep(CHECK_COOLDOWN)
        by_url = {}
        for r in suspect:
            by_url[r["url"]] = check_site(r["name"], r["url"], CHECK_TIMEOUT_RETRY)
            time.sleep(CHECK_RETRY_SPACING)
        results = [by_url.get(r["url"], r) for r in results]

    return results


def find_duplicates(results: list[dict]) -> list[dict]:
    """
    Find sites that are probably listed twice, and annotate them.

    The build already collapses addresses that differ only in spelling
    (trailing slash, www, scheme, case). What it cannot safely judge is
    whether two *different* addresses are the same destination, so those are
    reported for a person to decide rather than merged.

    Two signals, strongest first:

    - Same landing page. Two entries that end up at the same URL after
      redirects are the same destination, whatever they were listed as. This
      catches the cases spelling-matching misses: a bare domain alongside
      /index.html, or a host alongside the subdomain it forwards to.
    - Same host, different paths. Often two genuinely different pages, so it
      is offered as a review item and never as a conclusion.
    """
    groups: list[dict] = []

    by_final = defaultdict(list)
    for r in results:
        if r.get("final"):
            by_final[url_key(r["final"])].append(r)

    confirmed: set[int] = set()
    for key, rows in sorted(by_final.items()):
        if len(rows) < 2:
            continue
        groups.append({"kind": "same page", "key": key, "rows": rows})
        for r in rows[1:]:
            r["dupe_of"] = rows[0]["name"]
        confirmed.update(id(r) for r in rows)

    by_host = defaultdict(list)
    for r in results:
        if id(r) in confirmed:
            continue
        host = urlparse(r["url"]).netloc.lower().removeprefix("www.")
        by_host[host].append(r)

    for host, rows in sorted(by_host.items()):
        if len(rows) < 2:
            continue
        groups.append({"kind": "same host", "key": host, "rows": rows})

    return groups


def recommended_action(r: dict) -> str:
    """Plain-language next step for a finding, for the shareable report."""
    klass = r["klass"]
    if klass == "dead_dns":
        return "Domain is gone. Remove from the page and drop from the DOC whitelist."
    if klass == "parked":
        return "Domain expired. Remove from the page and drop from the DOC whitelist."
    if klass == "unreachable":
        return "Nothing responded. Confirm the site still exists, then remove or re-request."
    if klass == "server_error":
        return "Fault on the site's end. Contact the vendor; remove if it stays down."
    if klass == "client_error":
        return "Page not found. Find the current address and submit a DOC URL request."
    if klass in ("needs_www", "drop_www", "http_only"):
        return f"Correct the link to {r['suggest']} in data/url_overrides.json."
    if klass == "moved":
        return (
            "Test from inside a facility. If blocked, allow the destination host "
            "or submit a DOC URL request for it."
        )
    if klass == "blocked":
        return "None. The host answered; it refuses automated checks only."
    return "None."


def action_owner(r: dict) -> str:
    """Who has to do something about it."""
    klass = r["klass"]
    if klass == "moved":
        return "Facility testing"
    if klass in ("server_error", "client_error"):
        return "IT / vendor"
    if klass in ("dead_dns", "parked", "unreachable"):
        return "Remove from page"
    if klass in ("needs_www", "drop_www", "http_only"):
        return "Fix in build"
    return "None"


def link_report_lines(results: list[dict]) -> list[str]:
    """The grouped report as plain text lines, shared by console and .txt output."""
    grouped = defaultdict(list)
    for r in results:
        grouped[r["klass"]].append(r)

    width = min(max((len(r["name"]) for r in results), default=10), 38)
    lines: list[str] = []

    for klass, heading in CHECK_CLASSES:
        rows = grouped.get(klass)
        if not rows:
            continue
        lines.append("")
        lines.append(f"{heading} ({len(rows)})")
        if klass == "moved":
            lines.append("  (the listed URL works, but a filter that whitelists only the")
            lines.append("   original host will still block the page it lands on)")
        if klass == "blocked":
            lines.append("  (not evidence of breakage - these answered, so the host is alive)")
        if klass == "ok":
            continue
        for r in sorted(rows, key=lambda x: x["name"].lower()):
            lines.append(f"  {r['name'][:width]:<{width}}  {r['url']}")
            lines.append(f"  {'':<{width}}  {r['detail']}")
            if r["suggest"]:
                lines.append(f"  {'':<{width}}  -> suggested: {r['suggest']}")
            lines.append(f"  {'':<{width}}  ACTION: {recommended_action(r)}")

    dupes = find_duplicates(results)  # idempotent; also annotates dupe_of
    if dupes:
        same_page = [g for g in dupes if g["kind"] == "same page"]
        same_host = [g for g in dupes if g["kind"] == "same host"]
        lines.append("")
        lines.append(f"POSSIBLE DUPLICATES ({len(dupes)} group(s))")
        lines.append("  (spelling duplicates are already collapsed at build time;")
        lines.append("   these are different addresses that may be the same site)")
        for g in same_page:
            lines.append("")
            lines.append(f"  SAME LANDING PAGE -> {g['key']}")
            for r in g["rows"]:
                lines.append(f"      {r['name'][:width]:<{width}}  {r['url']}")
            lines.append(f"  {'':<{width}}  ACTION: same destination after redirects. "
                         f"Keep one; remove the rest via data/url_overrides.json.")
        for g in same_host:
            lines.append("")
            lines.append(f"  SAME HOST, DIFFERENT PATHS -> {g['key']}")
            for r in g["rows"]:
                lines.append(f"      {r['name'][:width]:<{width}}  {r['url']}")
            lines.append(f"  {'':<{width}}  ACTION: check whether these are genuinely "
                         f"different pages. Often they are; if not, keep one.")
    return lines


def write_report_txt(results: list[dict], path: str, source: str) -> None:
    """A plain-text report that can be pasted into an email or ticket."""
    broken = sum(1 for r in results if r["klass"] in CHECK_BROKEN)
    moved = sum(1 for r in results if r["klass"] == "moved")
    blocked = sum(1 for r in results if r["klass"] == "blocked")
    ok = len(results) - broken - moved - blocked

    head = [
        "APPROVED SITES LINK REVIEW",
        "=" * 60,
        f"Checked   : {datetime.now():%Y-%m-%d %H:%M}",
        f"Source    : {source}",
        f"Links     : {len(results)}",
        f"Summary   : {ok} OK, {broken} broken, {moved} redirecting off-host, "
        f"{blocked} blocked to automation",
        "",
        "Checked from a staff network, not from inside a facility. A site reachable",
        "here may still be blocked by the facility filter, and an internal-only host",
        "may fail here yet work there. This finds problems at the source; it does not",
        "replace testing from inside.",
    ]
    body = link_report_lines(results)

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(head + body) + "\n", encoding="utf-8")


def write_report_csv(results: list[dict], path: str) -> None:
    """One row per site, for a spreadsheet — sortable and filterable for review."""
    order = {k: i for i, (k, _) in enumerate(CHECK_CLASSES)}
    headings = dict(CHECK_CLASSES)

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "Site", "URL on page", "Status", "Finding",
            "Suggested URL", "Possible duplicate of", "Owner",
            "Recommended action", "Checked",
        ])
        today = f"{datetime.now():%Y-%m-%d}"
        for r in sorted(results, key=lambda x: (order.get(x["klass"], 99), x["name"].lower())):
            w.writerow([
                r["name"],
                r["url"],
                headings.get(r["klass"], r["klass"]).split("—")[0].strip(),
                r["detail"],
                r["suggest"] or "",
                r.get("dupe_of", ""),
                action_owner(r),
                recommended_action(r),
                today,
            ])


def print_link_report(results: list[dict]) -> None:
    for line in link_report_lines(results):
        print(line)


def write_link_suggestions(results: list[dict], path: str) -> int:
    """
    Write the unambiguous fixes as a url_overrides.json fragment to review and
    merge by hand. Deliberately not merged automatically: a redirect can point
    somewhere the site did not intend, and removals are a content decision.
    """
    replace, remove = {}, {}
    for r in results:
        key = url_key(r["url"])
        if r["klass"] in ("needs_www", "drop_www", "http_only", "moved") and r["suggest"]:
            replace[key] = {
                "url": r["suggest"],
                "note": f"{r['name']}: {r['detail']} (checked {datetime.now():%Y-%m-%d})",
            }
        elif r["klass"] in ("dead_dns", "parked"):
            remove[key] = f"{r['name']}: {r['detail']} (checked {datetime.now():%Y-%m-%d})"

    if not replace and not remove:
        return 0

    payload = {
        "_comment": (
            "Suggestions from --check-links. Review, then merge the entries you "
            f"want into {URL_OVERRIDES_FILE}. Not applied until you do."
        ),
        "replace": replace,
        "remove": remove,
    }
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return len(replace) + len(remove)


# ---------------------------------------------------------------------------
# Row resolution
# ---------------------------------------------------------------------------
def resolve_sites(rows: list[dict], url_replace: dict, url_remove: dict,
                  excluded: dict | None = None, announce: bool = True):
    """
    Turn CSV rows into the (name, url, row) list the page is built from.

    Applies, in order: skip blank rows, skip rows marked "removed", normalize
    the URL, drop excluded sites, drop sites named in the overrides' remove
    block, and rewrite those in its replace block.

    --check-links uses this too, so the checker tests exactly the links the
    page would carry rather than a second interpretation of the same rules.
    """
    sites: list[tuple[str, str, dict]] = []
    removed = replaced = duplicates = 0
    excluded = excluded or {}
    excluded_hits: dict[str, list[str]] = defaultdict(list)
    seen: set[str] = set()
    kept_by_key: dict[str, str] = {}
    total = len(rows)

    def say(msg: str):
        if not announce:
            return
        tqdm.write(msg) if HAS_TQDM else print(msg)

    for idx, row in enumerate(rows, start=1):
        name = str(row.get(TITLE_COLUMN) or "").strip()
        raw_url = str(row.get("Website_Url") or "").strip()

        if not name or not raw_url:
            say(f"[{idx}/{total}] Skipping empty row")
            continue

        if "removed" in name.lower() or "removed" in raw_url.lower():
            say(f"[{idx}/{total}] Skipping removed site: {name}")
            continue

        if not looks_like_url(raw_url):
            say(f"[{idx}/{total}] Skipping {name}: not a URL ({raw_url[:60]!r})")
            continue

        url = normalize_url(raw_url)

        # Sites withheld from students whatever DOC approves. Checked before the
        # overrides and again after them, so a URL correction can't route a
        # site onto an excluded host.
        entry = excluded_by(url, excluded)
        if entry:
            say(f"[{idx}/{total}] Excluding {name}: {excluded[entry]}")
            excluded_hits[entry].append(name)
            continue

        # Corrections for URLs that don't load as DOC exports them.
        key = url_key(url)
        seen.add(key)
        if key in url_remove:
            say(f"[{idx}/{total}] Removing {name}: {url_remove[key]}")
            removed += 1
            continue
        if key in url_replace and url_replace[key] != url:
            say(f"[{idx}/{total}] URL override: {url} -> {url_replace[key]}")
            url = url_replace[key]
            replaced += 1
            entry = excluded_by(url, excluded)
            if entry:
                say(f"[{idx}/{total}] Excluding {name}: {excluded[entry]}")
                excluded_hits[entry].append(name)
                continue

        # DOC lists some sites twice under separate whitelist IDs, differing
        # only by a trailing slash or a www prefix (epa.gov and liveabout.com
        # both do). They are one site to a student, so the page shows one tile.
        # Keyed the same way as URL overrides, so the two agree on what counts
        # as the same address.
        dupe_key = url_key(url)
        if dupe_key in kept_by_key:
            kept_name = kept_by_key[dupe_key]
            note = f" (listed as '{kept_name}')" if kept_name != name else ""
            say(f"[{idx}/{total}] Duplicate of {dupe_key}{note}: skipping {name} {url}")
            duplicates += 1
            continue
        kept_by_key[dupe_key] = name

        sites.append((name, url, row))

    return sites, {
        "removed": removed,
        "replaced": replaced,
        "seen": seen,
        "duplicates": duplicates,
        "excluded": dict(excluded_hits),
    }


# ---------------------------------------------------------------------------
# CSV selection
# ---------------------------------------------------------------------------
def csv_columns(path: Path) -> list[str]:
    """Read just the header row of a CSV. utf-8-sig strips a leading BOM."""
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            for row in csv.reader(f):
                return [c.strip() for c in row]
    except Exception:
        pass
    return []


def read_csv_rows(path: Path) -> tuple[list[dict], list[str]]:
    """
    Read a CSV into a list of row dicts, plus its column names.

    This was pandas, which earned its place twice: this read and one boolean
    mask. The stdlib does both, and dropping it takes pandas and numpy out of
    the install for a script that never indexes, joins or aggregates anything.

    Header names are stripped, because DOC exports pad some of them. A blank
    cell arrives as an empty string rather than pandas' NaN, which also fixes
    a row with no Title reading as the string "nan" and passing the
    not-empty check downstream.
    """
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        try:
            header = [str(c).strip() for c in next(reader)]
        except StopIteration:
            return [], []
        rows = [
            {header[i]: (cell if i < len(cell_row) else "")
             for i, cell in enumerate(cell_row[: len(header)])}
            for cell_row in reader
            if any(str(c).strip() for c in cell_row)
        ]
    # Fill columns a short row omitted, so every row has every key.
    for row in rows:
        for col in header:
            row.setdefault(col, "")
    return rows, header


def missing_columns(path: Path) -> list[str]:
    """Which required columns this CSV lacks (empty list = usable)."""
    cols = csv_columns(path)
    missing = []
    if TITLE_COLUMN not in cols:
        missing.append(TITLE_COLUMN)
    if not any(c in cols for c in URL_COLUMNS):
        missing.append(" or ".join(URL_COLUMNS))
    return missing


def list_csv_candidates(csv_dir: Path) -> list[tuple[Path, list[str]]]:
    """All CSVs in csv_dir, newest first, each paired with its missing columns."""
    paths = sorted(
        csv_dir.glob("*.csv"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return [(p, missing_columns(p)) for p in paths]


def choose_csv(csv_dir: Path) -> Path:
    """
    Pick the CSV to build from, interactively.

    The newest file in csv_dir is offered as the default; pressing Enter
    accepts it, or a number selects a different one. Files that lack the
    required columns are listed but flagged, and the default falls through
    to the newest usable file so Enter never selects a build that must fail.

    When stdin is not a terminal (CI, piped input) the default is used
    without prompting.
    """
    if not csv_dir.is_dir():
        raise SystemExit(
            f"No '{csv_dir}' directory found. Pass a CSV path explicitly, e.g.\n"
            f"  python build_approved_sites.py path/to/export.csv"
        )

    candidates = list_csv_candidates(csv_dir)
    if not candidates:
        raise SystemExit(
            f"No CSV files found in '{csv_dir}'. Add an export there, or pass a\n"
            f"path explicitly: python build_approved_sites.py path/to/export.csv"
        )

    # Default to the newest usable file; fall back to the newest overall.
    default_idx = next(
        (i for i, (_, missing) in enumerate(candidates) if not missing),
        0,
    )

    print(f"\n📁 CSV files in {csv_dir}/ (newest first):\n")
    width = max(len(p.name) for p, _ in candidates)
    for i, (path, missing) in enumerate(candidates):
        mtime = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        status = f"⚠ missing {', '.join(missing)}" if missing else "✓ usable"
        marker = "→" if i == default_idx else " "
        print(f" {marker} {i + 1}) {path.name:<{width}}  {mtime}  {status}")

    default_path = candidates[default_idx][0]

    if not sys.stdin.isatty():
        print(f"\nNot a terminal; using default: {default_path}\n")
        return default_path

    prompt = f"\nSelect a file [1-{len(candidates)}], or Enter for {default_idx + 1}) {default_path.name}: "
    while True:
        try:
            raw = input(prompt).strip()
        except EOFError:
            print()
            return default_path

        if not raw:
            print(f"Using: {default_path}\n")
            return default_path

        if raw.isdigit() and 1 <= int(raw) <= len(candidates):
            chosen = candidates[int(raw) - 1][0]
            print(f"Using: {chosen}\n")
            return chosen

        print(f"  Please enter a number from 1 to {len(candidates)}, or press Enter.")


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------
def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Build the approved websites page from a CSV export + template, "
                    "with descriptions, category overrides, and embedded favicons."
    )
    parser.add_argument(
        "csv",
        nargs="?",
        help=f"CSV export to build from. Omit to choose from {CSV_DIR}/ (newest first).",
    )
    parser.add_argument(
        "-t",
        "--template",
        default="template.html",
        help="HTML template file (default: template.html)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="Approved_Websites.html",
        help="Output HTML file (default: Approved_Websites.html)",
    )

    # Descriptions: the default scrapes only what is missing. Re-scraping
    # everything is an explicit choice because it takes the better part of an
    # hour and overwrites descriptions that may have been edited by hand.
    desc_group = parser.add_mutually_exclusive_group()
    desc_group.add_argument(
        "--refresh-descriptions",
        action="store_true",
        help="Re-scrape every site, replacing all cached descriptions. Slow, and it "
             "discards any hand-edited text in data/site_descriptions.json.",
    )
    desc_group.add_argument(
        "--no-descriptions",
        action="store_true",
        help="Disable scraping entirely: use the cache, then the CSV, then a generic "
             "fallback.",
    )
    desc_group.add_argument(
        "--descriptions-missing-only",
        action="store_true",
        help="Accepted for compatibility — this is now the default.",
    )

    parser.add_argument(
        "--check-links",
        action="store_true",
        help="Check every link and report dead, moved, www-only and http-only "
             "sites, then exit without building.",
    )
    parser.add_argument(
        "--report",
        metavar="PATH",
        help=f"With --check-links, write the findings to this exact file instead of "
             f"the timestamped pair in {LINK_REPORT_DIR}/. Format follows the "
             f"extension: .csv for a spreadsheet, anything else plain text.",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help=f"With --check-links, don't write report files to {LINK_REPORT_DIR}/.",
    )
    parser.add_argument(
        "--all-categories",
        action="store_true",
        help=f"Build every row, instead of only those whose '{CATEGORY_COLUMN}' "
             f"mentions '{CATEGORY_FILTER}'.",
    )

    # Run history. Every build and every --check-links run is recorded to
    # data/build_history.db, which is what makes the trend report possible.
    parser.add_argument(
        "--trends",
        action="store_true",
        help=f"Write the trend report ({trend_report.OUTPUT}) from the recorded run "
             f"history and exit, without building or checking anything.",
    )
    parser.add_argument(
        "--no-history",
        action="store_true",
        help="Don't record this run in the history database.",
    )
    parser.add_argument(
        "--backfill-history",
        action="store_true",
        help="Seed the history from past builds found on disk and in git, then exit. "
             "Safe to re-run; runs already recorded are left alone.",
    )

    # Favicons: default = embed favicons.
    parser.add_argument(
        "--no-embed-favicons",
        action="store_true",
        help="Disable favicon fetching (no data: URLs).",
    )

    args = parser.parse_args(argv)

    if (args.report or args.no_report) and not args.check_links:
        parser.error("--report and --no-report only apply to --check-links.")
    if args.report and args.no_report:
        parser.error("--report and --no-report contradict each other.")
    if args.trends and args.check_links:
        parser.error("--trends reports on past runs; it cannot be combined with --check-links.")

    # Both of these work purely from recorded history, so neither needs a CSV,
    # a template, or a network.
    if args.backfill_history:
        print("Seeding run history from past builds on disk and in git...\n")
        summary = history_backfill.backfill(
            check_classes=CHECK_CLASSES,
            broken_classes=CHECK_BROKEN,
        )
        print(
            f"\nRecorded {summary['builds']} build(s) and {summary['checks']} link check(s)."
        )
        if summary["builds_already_present"] or summary["checks_already_present"]:
            print(
                f"Left alone: {summary['builds_already_present']} build(s) and "
                f"{summary['checks_already_present']} link check(s) already recorded."
            )
        if summary["pages_unparseable"]:
            print(
                f"Skipped {summary['pages_unparseable']} HTML file(s) that this builder "
                f"did not generate."
            )
        print(f"\nNow run --trends to write {trend_report.OUTPUT}.")
        return

    if args.trends:
        summary = trend_report.render(broken_classes=CHECK_BROKEN)
        print(
            f"Wrote {summary['output']} from {summary['builds']} build(s) and "
            f"{summary['link_checks']} link check(s)."
        )
        print(f"Latest build: {summary['latest_total']} approved sites.")
        if summary["problems"]:
            print(f"{summary['problems']} link(s) flagged by the most recent check.")
        return

    template_path = Path(args.template)
    if not template_path.exists():
        raise SystemExit(f"Template not found: {template_path}")

    if args.csv:
        csv_path = Path(args.csv)
        if not csv_path.exists():
            raise SystemExit(f"CSV not found: {csv_path}")
    else:
        csv_path = choose_csv(Path(CSV_DIR))

    rows, columns = read_csv_rows(csv_path)
    # Kept for the history record: whether the export could be filtered at all,
    # and how many rows it offered before anything was dropped.
    original_columns = set(columns)
    total_export_rows = len(rows)

    missing = []
    if TITLE_COLUMN not in columns:
        missing.append(TITLE_COLUMN)
    url_col = next((c for c in URL_COLUMNS if c in columns), None)
    if url_col is None:
        missing.append(" or ".join(URL_COLUMNS))
    if missing:
        raise SystemExit(
            f"{csv_path} is missing required column(s): {', '.join(missing)}.\n"
            f"Found: {', '.join(columns)}"
        )

    # Work with one canonical URL column downstream. Copying onto Website_Url
    # overwrites whatever was there, which is what the old drop-then-rename did.
    if url_col != "Website_Url":
        for row in rows:
            row["Website_Url"] = row.get(url_col, "")
        print(f"Using '{url_col}' as the site URL column.")

    # Keep education rows only (unless the export doesn't say, or --all-categories).
    rows_skipped_category = 0
    if args.all_categories:
        print("Category filter disabled: building every row in the export.")
    elif CATEGORY_COLUMN in columns:
        needle = CATEGORY_FILTER.lower()
        kept = [
            r for r in rows
            if needle in str(r.get(CATEGORY_COLUMN) or "").lower()
        ]
        dropped = len(rows) - len(kept)
        rows_skipped_category = dropped
        rows = kept
        print(f"Category filter '{CATEGORY_FILTER}': kept {len(rows)} rows, skipped {dropped}.")
        if not rows:
            raise SystemExit(
                f"No rows in {csv_path} have a '{CATEGORY_COLUMN}' containing "
                f"'{CATEGORY_FILTER}'. Use --all-categories to build the export as-is."
            )
    else:
        print(
            f"Note: no '{CATEGORY_COLUMN}' column in {csv_path.name}; "
            f"building every row (cannot filter to {CATEGORY_FILTER})."
        )

    if not HAS_TQDM:
        print("Note: tqdm is not installed. Run 'pip install tqdm' to get a fancy progress bar.")
        print("Proceeding with simple progress output.\n")

    descriptions = load_descriptions()
    category_changes = load_category_changes()
    url_replace, url_remove = load_url_overrides()
    excluded_sites = load_excluded_sites()

    # Default: fill in what is missing and leave cached descriptions alone.
    # --descriptions-missing-only asks for exactly this, and is kept as a no-op
    # so existing habits and scripts keep working.
    force_regen = args.refresh_descriptions
    generate_missing = not args.no_descriptions

    # Favicons: default embed, unless explicitly disabled
    embed_favicons = not args.no_embed_favicons

    categorized: dict[str, list] = defaultdict(list)
    has_desc_col = "Website_Description" in columns

    scraped_count = 0
    cached_count = 0
    disabled_count = 0

    sites, resolve_stats = resolve_sites(rows, url_replace, url_remove, excluded_sites)
    removed_by_override = resolve_stats["removed"]
    duplicate_rows = resolve_stats["duplicates"]
    replaced_by_override = resolve_stats["replaced"]
    seen_url_keys = resolve_stats["seen"]
    excluded_hits = resolve_stats["excluded"]

    if args.check_links:
        results = run_link_check(sites)
        print_link_report(results)  # annotates dupe_of on the way through

        if args.report:
            if Path(args.report).suffix.lower() == ".csv":
                write_report_csv(results, args.report)
                print(f"\nWrote spreadsheet report to {args.report}")
            else:
                write_report_txt(results, args.report, str(csv_path))
                print(f"\nWrote text report to {args.report}")
        elif not args.no_report:
            stamp = f"{datetime.now():%Y%m%d-%H%M}"
            base = Path(LINK_REPORT_DIR) / f"link-review-{stamp}"
            write_report_csv(results, str(base.with_suffix(".csv")))
            write_report_txt(results, str(base.with_suffix(".txt")), str(csv_path))
            print(f"\nWrote report to {base}.csv")
            print(f"           and {base}.txt")

        written = write_link_suggestions(results, URL_SUGGESTIONS_FILE)
        broken = sum(1 for r in results if r["klass"] in CHECK_BROKEN)
        moved = sum(1 for r in results if r["klass"] == "moved")
        blocked = sum(1 for r in results if r["klass"] == "blocked")
        ok = len(results) - broken - moved - blocked
        print(
            f"\n{ok} OK, {broken} broken, {moved} redirecting off-host, "
            f"{blocked} blocked to automation (of {len(results)})."
        )
        if written:
            print(f"Wrote {written} suggested override(s) to {URL_SUGGESTIONS_FILE}.")
            print(f"Review them, then merge the ones you want into {URL_OVERRIDES_FILE}.")
        # As with a build: the reports are already on disk by now, so a problem
        # recording the run is worth reporting but not worth failing over.
        if not args.no_history:
            try:
                history.record_link_check(
                    results=results,
                    broken_classes=CHECK_BROKEN,
                    source_csv=str(csv_path),
                )
                print(f"Recorded this check in {history.DB_PATH}.")
            except Exception as e:
                print(f"Warning: could not record this check in {history.DB_PATH}: {e}")

        print(
            "\nNote: checked from this machine, not from inside a facility. A site "
            "reachable here\nmay still be blocked by the facility filter, and an "
            "internal-only host may fail here\nyet work there. This finds dead and "
            "moved sites; it does not replace facility testing."
        )
        return

    # Progress is now counted over the sites that survived resolution, not
    # every CSV row, so the numbers match the work actually being done.
    total_rows = len(sites)

    if HAS_TQDM:
        iterator = enumerate(
            tqdm(sites, total=total_rows, desc="Processing sites", unit="site"),
            start=1,
        )
    else:
        iterator = enumerate(sites, start=1)

    for idx, (name, url, row) in iterator:
        row_desc = ""
        if has_desc_col:
            row_desc = str(row.get("Website_Description") or "")

        # Ask the same question the picker will ask, so the line printed here
        # describes the work that is about to happen.
        desc_mode = description_mode(url, descriptions, generate_missing, force_regen)
        if desc_mode == "cached":
            cached_count += 1
        elif desc_mode == "scrape":
            scraped_count += 1
        else:
            disabled_count += 1

        msg_prefix = f"[{idx}/{total_rows}]"
        if desc_mode == "fallback":
            msg = f"{msg_prefix} No description available: {name}"
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

        # Use description-aware categorization (with manual overrides)
        category = get_category_for_site(name, url, desc, category_changes)

        categorized[category].append((name, url, desc))

    # Drop cache entries whose key was never an address. Four of these existed,
    # keyed by prose out of a bad export ("Link is in place for mandatory
    # entry..."); looks_like_url now stops new ones arriving, and this clears
    # any already there. Safe to do unconditionally: no real site can ever have
    # one of these keys.
    junk_keys = [k for k in descriptions if not looks_like_url(k)]
    for key in junk_keys:
        del descriptions[key]
    if junk_keys:
        print(f"\nDropped {len(junk_keys)} cached description(s) not keyed by a URL:")
        for key in junk_keys:
            print(f"  {key[:72]}")

    # Entries for sites this build didn't touch are only reported, never
    # removed. With the category filter on, "not in this build" means "not an
    # education row", not "not needed" — pruning here would quietly throw away
    # the reentry and vet-program descriptions.
    stale = [k for k in descriptions if k not in {url for _, url, _ in sites}]

    # Persist JSON sidecars
    save_descriptions(descriptions)

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

    write_text_atomic(Path(args.output), html_out)

    print()
    print(f"Wrote {args.output} with {total_sites} sites across {total_categories} categories.")
    if args.no_descriptions:
        print("Descriptions: scraping DISABLED (cache, then CSV, then a generic line).")
    elif args.refresh_descriptions:
        print("Descriptions: re-scraped for ALL sites (--refresh-descriptions).")
    else:
        print("Descriptions: scraped only where missing; cached text kept (default).")

    print(
        f"Description summary: scraped={scraped_count}, cached={cached_count}, "
        f"fallback={disabled_count}"
    )
    if stale:
        print(
            f"  ({len(stale)} cached description(s) are for sites not in this build — "
            f"kept, since the category filter alone explains most of them.)"
        )

    if duplicate_rows:
        print(f"Duplicates: {duplicate_rows} row(s) skipped as the same site listed twice.")

    if url_replace or url_remove:
        print(
            f"URL overrides: {replaced_by_override} link(s) corrected, "
            f"{removed_by_override} site(s) removed."
        )
        unused = sorted(
            (set(url_replace) | set(url_remove)) - seen_url_keys
        )
        for k in unused:
            print(f"  Note: override '{k}' matched nothing in this export.")

    if excluded_sites:
        count = sum(len(v) for v in excluded_hits.values())
        print(f"Excluded sites: {count} row(s) withheld ({EXCLUDED_SITES_FILE}).")
        # Unlike a URL override, an unmatched exclusion is not stale: DOC may
        # list the site again in a later export, and the entry must be there
        # when it does. So this is reported, not flagged for cleanup.
        for entry in sorted(excluded_sites):
            names = excluded_hits.get(entry)
            if names:
                print(f"  {entry}: withheld {', '.join(names)}")
            else:
                print(f"  {entry}: not in this export")

    if embed_favicons:
        print("Favicons: embedded as data: URLs (default).")
    else:
        print("Favicons: fetching DISABLED.")

    # Record the run, so the counts above become a series rather than something
    # that scrolls off the terminal. A failure here must not lose a page that is
    # already written to disk, so it is reported and otherwise ignored.
    if not args.no_history:
        recorded = [
            (name, url, category)
            for category, entries in categorized.items()
            for name, url, _ in entries
        ]
        try:
            history.record_build(
                sites=recorded,
                counts={
                    "export_rows": total_export_rows,
                    "rows_skipped_category": rows_skipped_category,
                    "duplicates_collapsed": duplicate_rows,
                    "removed_by_override": removed_by_override,
                    "replaced_by_override": replaced_by_override,
                    "descriptions_scraped": scraped_count,
                    "descriptions_cached": cached_count,
                },
                source_csv=str(csv_path),
                output_file=args.output,
                # The same stamp the page itself carries, not "now". Recording
                # happens after the favicon pass, which can run for minutes, so
                # a fresh timestamp here would not match the one written into
                # the page — and --backfill-history, which reads that stamp
                # back out of generated pages, would record this very build a
                # second time as a reconstructed duplicate.
                ran_at=f"{last_updated}:00",
                category_filter="" if args.all_categories else (
                    CATEGORY_FILTER if CATEGORY_COLUMN in original_columns else ""
                ),
            )
            print(f"History: recorded this build in {history.DB_PATH}.")
            print(f"         Run --trends to refresh {trend_report.OUTPUT}.")
        except Exception as e:
            print(f"Warning: could not record this build in {history.DB_PATH}: {e}")


if __name__ == "__main__":
    main()
