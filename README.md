# Approved Websites Page – Corrections Education

Generates a single, self-contained HTML page listing the DOC-approved websites
available to incarcerated students. The page is a static file with no backend:
it is built here, then served however you choose (static host, file share,
local web server on the education network).

---

## What it produces

`Approved_Websites.html` — one file containing every approved site, grouped into
categories, with favicons embedded as `data:` URLs. No external requests are
made when a student opens it, so it works on a fully isolated network.

The page itself provides:

- Search across site names, URLs and descriptions
- Category navigation sidebar
- Favorites, saved in the browser with drag-and-drop ordering
- Light / dark / system theme, and list / grid views

Everything is client-side. Nothing is tracked, transmitted or shared between
users — favorites live only in that browser's local storage.

---

## Building the page

Install dependencies once:

```bash
pip install -r requirements.txt
```

Then build:

```bash
python build_approved_sites.py
```

With no arguments it lists the CSV exports in `site_extracts/`, newest first,
and offers the newest usable one as the default — press Enter to accept it, or
type a number to build from a different export:

```
📁 CSV files in site_extracts/ (newest first):

   1) OSN URL Filtering.csv       2026-09-15 11:13  ⚠ missing Website_Url
 → 2) reconciled_20260709.csv     2026-07-09 09:35  ✓ usable
   3) All OSN approved sites.csv  2026-07-09 08:36  ⚠ missing Website_Url

Select a file [1-3], or Enter for 2) reconciled_20260709.csv:
```

To skip the prompt, name the file directly:

```bash
python build_approved_sites.py site_extracts/reconciled_20260709.csv
```

When stdin isn't a terminal (scripts, CI) the default is used without prompting.

### CSV format

The export must have a `Title` column and a `Website_Url` column. Files missing
either are flagged in the picker rather than failing mid-build.

Note that raw OSN exports currently use `Website` rather than `Website_Url`, so
they need that column renamed before use — `reconciled_20260709.csv` is an
example of an already-converted export.

Rows are skipped when the title or URL is blank, or when either contains
"removed".

---

## Options

| Flag | Effect |
|---|---|
| `-o`, `--output` | Output file (default: `Approved_Websites.html`) |
| `-t`, `--template` | Template file (default: `template.html`) |
| `--descriptions-missing-only` | Only fetch descriptions for sites not already cached |
| `--no-descriptions` | Don't fetch any descriptions; use the cache, then the CSV, then a generic fallback |
| `--no-embed-favicons` | Don't fetch or embed favicons |

By default the build re-fetches a description for **every** site, which visits
each one in turn with a polite delay — expect it to take a while. For a quick
rebuild after editing categories or the template:

```bash
python build_approved_sites.py --no-descriptions --no-embed-favicons
```

---

## Categories

Each site is placed by keyword scoring against its URL (+3), title (+2) and
description (+1), using the `category_keywords` lists near the top of
`build_approved_sites.py`. No keyword match means `Other`.

To correct a single site without touching the keyword lists, add an entry to
`data/category_changes.json`:

```json
[
  {
    "site_name": "Seattle Business Magazine",
    "site_url": "https://seattlebusinessmag.com/",
    "new_category": "Technology",
    "status": "applied"
  }
]
```

Overrides are matched on `site_name` **and** `site_url`, and only apply when
`status` is `"applied"`.

---

## Files

```
├── build_approved_sites.py     # CSV → HTML generator
├── template.html               # Page template + all CSS/JS
├── Approved_Websites.html      # Generated output
├── site_extracts/              # CSV exports (gitignored)
└── data/
    ├── site_descriptions.json  # Cached descriptions, keyed by URL
    └── category_changes.json   # Manual category overrides
```

`data/site_descriptions.json` is the scrape cache — keep it, or every build
re-visits all ~137 sites. It's updated in place on each run.

**`site_extracts/` is gitignored** (`*.csv`), so CSV exports are not in the
repo. Colleagues cloning this will need an export from you before they can
build.

---

## Serving the page

`Approved_Websites.html` is fully self-contained — copy it wherever it needs to
be served from. It requires no server-side code, no network access from the
client, and no build step at view time.
