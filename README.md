# Approved Websites Page – Corrections Education

Generates a single, self-contained HTML page listing the DOC-approved websites
available to incarcerated students. The page is a static file with no backend:
it is built here, then served however you choose (static host, file share,
local web server on the education network).

---

## What it produces

`Approved_Websites.html` — one file listing the DOC-approved sites tagged for
education, grouped into categories, with favicons embedded as `data:` URLs. No
external requests are made when a student opens it, so it works on a fully
isolated network.

The page itself provides:

- Search across site names, URLs and descriptions
- Category navigation sidebar
- Favorites, saved in the browser with drag-and-drop ordering
- Light / dark / system theme, and list / grid views

Everything is client-side. Nothing is tracked, transmitted or shared between
users — favorites live only in that browser's local storage.

---

## Building the page

Needs Python 3.10 or newer. Install dependencies once:

```bash
pip install -r requirements.txt
```

Then build:

```bash
python build_approved_sites.py
```

Run it as a script, not a module — `python -m build_approved_sites.py` fails,
because `-m` takes a module name rather than a filename. (`python -m
build_approved_sites`, without the `.py`, does work.)

With no arguments it lists the CSV exports in `site_extracts/`, newest first,
and offers the newest as the default — press Enter to accept it, or type a
number to build from a different export:

```
📁 CSV files in site_extracts/ (newest first):

 → 1) OSN URL Filtering.csv       2026-09-15 11:13  ✓ usable
   2) reconciled_20260709.csv     2026-07-09 09:35  ✓ usable
   3) All OSN approved sites.csv  2026-07-09 08:36  ✓ usable

Select a file [1-3], or Enter for 1) OSN URL Filtering.csv:
```

To skip the prompt, name the file directly:

```bash
python build_approved_sites.py "site_extracts/OSN URL Filtering.csv"
```

When stdin isn't a terminal (scripts, CI) the default is used without prompting.

### CSV format

The export must have a `Title` column and a URL column named either `Website`
(what DOC exports use) or `Website_Url` (older, hand-converted exports). Either
works as-is, with no manual renaming; when both are present, `Website` wins.
Files missing a usable column are flagged in the picker rather than failing
mid-build.

Extra columns — `ID`, `Associated URLs`, `Authorizing SR` — are ignored, and a
leading BOM is handled. `URL Category` is used to filter (see below).

Rows are skipped when the title or URL is blank, or when either contains
"removed".

### Education rows only

DOC exports tag each row with the whitelists it belongs to:

```
["IncarEducation"]
["IncarEducation","IncarVetProgramWhitelist"]
["IncarReentry"]
```

This page covers education, so only rows whose `URL Category` mentions
**`IncarEducation`** are built. Everything else — reentry, vet program, law
library — is skipped, and the build prints the counts:

```
Category filter 'IncarEducation': kept 104 rows, skipped 38.
```

Matching is on the text, so `IncarEducationStudent` and `IncarEducationStaffURL`
are included too.

Exports with no `URL Category` column (such as the older converted files) can't
be filtered and are built in full, with a note. `--all-categories` skips the
filter entirely.

---

## Options

| Flag | Effect |
|---|---|
| `-o`, `--output` | Output file (default: `Approved_Websites.html`) |
| `-t`, `--template` | Template file (default: `template.html`) |
| `--descriptions-missing-only` | Only fetch descriptions for sites not already cached |
| `--no-descriptions` | Don't fetch any descriptions; use the cache, then the CSV, then a generic fallback |
| `--no-embed-favicons` | Don't fetch or embed favicons |
| `--all-categories` | Build every row, not just `IncarEducation` ones |
| `--check-links` | Check every link and report problems, then exit without building |
| `--report PATH` | With `--check-links`, also write the findings to a file (`.csv` or text) |

### Which one to use

**For a normal rebuild, use `--descriptions-missing-only`:**

```bash
python build_approved_sites.py --descriptions-missing-only
```

It reuses the cached descriptions and scrapes only sites it hasn't seen, so a
rebuild takes a minute rather than the better part of an hour.

This matters beyond speed. The **default** re-scrapes every site and
**overwrites `data/site_descriptions.json`**, discarding any hand-editing done
to those descriptions. Use the bare command only when you actually want every
description regenerated from scratch.

For a quick check with no network at all — template edits, category tuning:

```bash
python build_approved_sites.py --descriptions-missing-only --no-embed-favicons
```

### When a new export arrives

1. Drop the CSV into `site_extracts/`.
2. Run `python build_approved_sites.py --descriptions-missing-only` and press
   Enter to take the newest file.
3. Read the build output: it names any site dropped as "removed", every URL
   override applied, and any override that no longer matches anything.
4. Commit the regenerated `Approved_Websites.html` and publish it.

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

## Fixing broken links

DOC exports sometimes carry URLs that don't load as written — a missing `www`,
a host that has moved, a site that has expired. Correct them in
`data/url_overrides.json` rather than in the generated page, so the fix
survives the next export:

```json
{
  "replace": {
    "ctclink.us": {
      "url": "https://gateway.ctclink.us/",
      "note": "why this was changed, and when it was verified"
    }
  },
  "remove": {
    "osibridge.com": "why this site was dropped"
  }
}
```

`replace` rewrites the link; `remove` drops the site from the page entirely.
Matching ignores scheme, `www.`, case and any trailing slash, so
`ctclink.us` matches `https://www.ctclink.us/` too. The build reports what it
applied, and warns about any override that matched nothing — which is how you
notice DOC has since fixed or dropped an entry:

```
[28/104] URL override: https://ctclink.us/ -> https://gateway.ctclink.us/
[69/104] Removing OSI Bridge: Site expired - serves a Squarespace placeholder.
URL overrides: 4 link(s) corrected, 2 site(s) removed.
```

Sites removed this way stay approved by DOC — they're just hidden from the
page. A site that needs to come back should be re-requested through DOC, or
the entry deleted from this file once the URL works again.

---

## Checking links

```bash
python build_approved_sites.py --check-links
```

Checks every link the page would carry — after the category filter and URL
overrides, so it tests exactly what students would click — and exits without
building. Takes about a minute for ~100 sites.

Results are grouped by cause, worst first:

| Group | Meaning |
|---|---|
| **DEAD** | Host has no address record. The domain is gone. |
| **EXPIRED / PARKED** | Responds, but serves a placeholder — a 200 is not proof of life. |
| **UNREACHABLE** | Nothing answered on any variant. |
| **SERVER ERROR / NOT FOUND** | 5xx, or a genuine 404. |
| **NEEDS www / DROP www / NO HTTPS** | The listed URL fails but an obvious variant works. |
| **REDIRECTS OFF-HOST** | The link works, but lands on a different host. |
| **BLOCKED TO AUTOMATION** | 401/403/429 — the host answered, so it's alive. |

Two of those deserve attention:

**REDIRECTS OFF-HOST** is easy to dismiss, because the link works fine from a
normal network. On a filtered network it may not: if the filter whitelists
`careercruising.com` and the site redirects to `public.careercruising.com`,
students hit a block even though nothing is "broken". This is a likely cause of
"the page doesn't load" reports where the URL looks correct.

**BLOCKED TO AUTOMATION** is not breakage. Many government and news sites
return 403 to anything that isn't a browser. They are listed so you can check
them by hand, not because anything is wrong.

### Sharing the results

To send the findings to IT or to a facility for testing, write them to a file:

```bash
python build_approved_sites.py --check-links --report link-review.csv
python build_approved_sites.py --check-links --report link-review.txt
```

The format follows the extension — `.csv` for a spreadsheet, anything else
plain text. Both carry the same findings; the spreadsheet adds one row per
site with **Owner** and **Recommended action** columns, so it can be sorted
and assigned:

| Site | URL on page | Status | Finding | Suggested URL | Owner | Recommended action |
|---|---|---|---|---|---|---|
| Magic School | `magicschool.com` | NOT FOUND | HTTP 404 | | IT / vendor | Find the current address and submit a DOC URL request |
| Worksource Washington | `www.worksourcewa.com` | REDIRECTS OFF-HOST | lands on `worksource.my.site.com` | `worksource.my.site.com/worksourcewa/` | Facility testing | Test from inside; if blocked, request the destination host |

The CSV is written with a BOM so Excel opens it as UTF-8 without mangling
accents. Note that `*.csv` is gitignored, so a report written into the repo
folder won't be committed by accident.

Unambiguous fixes are also written to `data/url_overrides.suggested.json` as a
ready-to-merge fragment. Nothing is applied automatically — a redirect can lead
somewhere the site didn't intend, and removing an approved site is a content
decision. Review it, move what you want into `data/url_overrides.json`, and
rebuild.

### What it can't tell you

It checks from **your** machine, not from inside a facility. A site reachable
here can still be blocked by the facility filter, and an internal-only host can
fail here yet work there. It finds origin-side rot — dead domains, expired
sites, moved hosts — which is the problem that accumulates quietly between
exports. It does not replace testing from inside.

---

## Favicons

Each site's icon is embedded in the page as a `data:` URL, so no icon is
fetched when a student opens it. The build tries, in order:

1. Google's favicon service, retried once after a pause — across a hundred-plus
   sites it intermittently refuses a request that succeeds on its own, and
   without the retry one blip permanently blanks a fetchable icon
2. the page's own `<link rel="icon">`
3. `/favicon.ico` on the site's origin, without following redirects to another
   host, so a bare domain that 404s onto `www` can't return the wrong icon

The image type comes from the bytes, not the `Content-Type` header — some
servers label a `.ico` as `text/plain`, and a browser won't render
`<img src="data:text/plain;...">`. HTML error pages and empty responses are
rejected rather than embedded.

Sites that serve no icon at all simply have none; that's cosmetic. **A favicon
is not evidence a site is reachable** — an expired domain parked on a hosting
provider still serves that provider's icon. Use `--no-embed-favicons` to skip
fetching entirely.

---

## Files

```
├── build_approved_sites.py     # CSV → HTML generator
├── template.html               # Page template + all CSS/JS
├── Approved_Websites.html      # Generated output
├── site_extracts/              # CSV exports (gitignored)
└── data/
    ├── site_descriptions.json  # Cached descriptions, keyed by URL
    ├── category_changes.json   # Manual category overrides
    └── url_overrides.json      # Link corrections and removals
```

`data/site_descriptions.json` is the scrape cache — keep it, or every build
re-visits every site in the export. It's updated in place on each run.

**`site_extracts/` is gitignored** (`*.csv`), so CSV exports are not in the
repo. Colleagues cloning this will need an export from you before they can
build.

---

## Serving the page

`Approved_Websites.html` is fully self-contained — copy it wherever it needs to
be served from. It requires no server-side code, no network access from the
client, and no build step at view time.
