"""
Seed the run history from what is already on disk and in git.

Trend data is worthless until there is history, and this project has eleven
months of it lying around unrecorded: every generated page carries its own site
count, category count and "Last Updated" stamp, and past builds were committed.
So the early part of the series can be reconstructed rather than waited for.

Sources, in the order they are searched:

  1. the current generated page (Approved_Websites.html)
  2. local_backups/*.html
  3. every generated page ever committed, read straight out of git

Every run recorded here is flagged `reconstructed = 1`. These are real builds
with real counts, but they were read back off a file rather than measured while
running, so the report labels them rather than passing them off as observed.

One caveat is recorded as a note rather than left for the reader to trip over:
builds before 2026-09-16 08:50 predate the IncarEducation filter (commit
e6cd466), so they count the whole approved whitelist. Without that note the
chart looks like 137 sites were removed in September, when the scope of the
page simply narrowed to education.
"""

import re
import subprocess
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup

import history
from urlkeys import url_key

# Builds before this moment counted the full whitelist, not education only.
# Boundary is commit e6cd466 "Build only rows tagged IncarEducation".
CATEGORY_FILTER_FROM = "2026-09-16 08:50:22"
PRE_FILTER_NOTE = (
    "Predates the IncarEducation filter (added 2026-09-16); "
    "counts the full DOC-approved whitelist, not education rows only."
)

GENERATED_PAGE_NAMES = (
    "Approved_Websites.html",
    "approved_websites.html",
    "index.html",
)


# ---------------------------------------------------------------------------
# Parsing a generated page
# ---------------------------------------------------------------------------
def parse_built_page(html: str) -> dict | None:
    """
    Pull a build's own record out of a page it generated.

    Returns None when the HTML is not one of our generated pages — early
    hand-written versions of this page exist in git and carry none of the
    markup, and they should be skipped rather than recorded as a zero-site
    build.
    """
    stamp_match = re.search(
        r"Last Updated:\s*</strong>\s*([0-9]{4}-[0-9]{2}-[0-9]{2}[ T][0-9]{2}:[0-9]{2})",
        html,
    )
    if not stamp_match:
        return None

    soup = BeautifulSoup(html, "html.parser")
    sections = soup.select("div.category-section")
    if not sections:
        return None

    sites: list[tuple[str, str, str]] = []
    for section in sections:
        title = section.select_one("h2.category-title")
        category = title.get_text(strip=True) if title else (section.get("id") or "Other")
        for item in section.select("li.site-item"):
            name_el = item.select_one(".site-name")
            url_el = item.select_one(".site-url")
            if not name_el or not url_el:
                continue
            name = name_el.get_text(strip=True)
            url = url_el.get_text(strip=True)
            if name and url:
                sites.append((name, url, category))

    if not sites:
        return None

    stated_total = re.search(r"Total Websites:\s*</strong>\s*([0-9]+)", html)
    ran_at = stamp_match.group(1).replace("T", " ") + ":00"

    return {
        "ran_at": ran_at,
        "sites": sites,
        "stated_total": int(stated_total.group(1)) if stated_total else None,
    }


def _record_page(parsed: dict, source_label: str, db_path: str) -> bool:
    """Record one reconstructed build, unless that timestamp is already there."""
    if history.run_exists("build_runs", parsed["ran_at"], db_path):
        return False

    pre_filter = parsed["ran_at"] < CATEGORY_FILTER_FROM
    notes = [PRE_FILTER_NOTE] if pre_filter else []

    stated = parsed["stated_total"]
    if stated is not None and stated != len(parsed["sites"]):
        # Worth surfacing rather than silently trusting one of the two numbers.
        notes.append(
            f"Page states {stated} sites; {len(parsed['sites'])} were parsed out of it."
        )

    distinct = len({url_key(url) for _, url, _ in parsed["sites"]})
    if distinct != len(parsed["sites"]):
        notes.append(
            f"Page listed {len(parsed['sites'])} sites at {distinct} distinct addresses — "
            "built before spelling duplicates were collapsed (commit f60f156)."
        )
    note = " ".join(notes)

    history.record_build(
        sites=parsed["sites"],
        counts={},
        source_csv="",
        output_file=source_label,
        category_filter="" if pre_filter else history_filter_label(),
        ran_at=parsed["ran_at"],
        reconstructed=True,
        note=note,
        db_path=db_path,
    )
    return True


def history_filter_label() -> str:
    """The category filter in force for post-2026-09-16 builds."""
    return "IncarEducation"


# ---------------------------------------------------------------------------
# Finding pages
# ---------------------------------------------------------------------------
def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=True
    ).stdout


def committed_pages() -> list[tuple[str, str]]:
    """
    Every generated page ever committed, as (label, html).

    Reads blobs straight out of git rather than checking anything out, so the
    working tree is never touched.
    """
    try:
        listing = _git(
            "log", "--all", "--diff-filter=AM", "--format=%H", "--name-only", "--", "*.html"
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []

    pairs: list[tuple[str, str]] = []
    commit = None
    for line in listing.splitlines():
        line = line.strip()
        if not line:
            continue
        if re.fullmatch(r"[0-9a-f]{40}", line):
            commit = line
        elif commit and Path(line).name in GENERATED_PAGE_NAMES:
            pairs.append((f"{commit[:7]}:{line}", f"{commit}:{line}"))

    out = []
    for label, spec in pairs:
        try:
            out.append((label, _git("show", spec)))
        except subprocess.CalledProcessError:
            continue
    return out


# ---------------------------------------------------------------------------
# Link reports
# ---------------------------------------------------------------------------
def parse_link_report(txt_path: Path, csv_path: Path | None, class_headings: dict) -> dict | None:
    """
    Rebuild a link-check run from the report files it wrote.

    The .txt header carries the run's totals and source; the .csv beside it
    carries one row per site, which is what makes "how long has this been
    broken" answerable for checks that ran before the database existed.
    """
    text = txt_path.read_text(encoding="utf-8", errors="replace")

    checked = re.search(r"Checked\s*:\s*([0-9-]{10} [0-9:]{5})", text)
    if not checked:
        return None
    source = re.search(r"Source\s*:\s*(.+)", text)
    total = re.search(r"Links\s*:\s*([0-9]+)", text)

    results: list[dict] = []
    if csv_path and csv_path.exists():
        import csv as csv_mod

        with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
            for row in csv_mod.DictReader(f):
                status = (row.get("Status") or "").strip()
                results.append({
                    "name": (row.get("Site") or "").strip(),
                    "url": (row.get("URL on page") or "").strip(),
                    "klass": class_headings.get(status, "ok"),
                    "detail": (row.get("Finding") or "").strip(),
                    "suggest": (row.get("Suggested URL") or "").strip(),
                })

    if not results:
        # No per-site CSV: record the totals from the text header alone, so the
        # run still appears on the trend even without its detail.
        return {
            "ran_at": checked.group(1) + ":00",
            "source_csv": source.group(1).strip() if source else "",
            "results": [],
            "totals": _parse_summary(text, total),
        }

    return {
        "ran_at": checked.group(1) + ":00",
        "source_csv": source.group(1).strip() if source else "",
        "results": results,
        "totals": None,
    }


def _parse_summary(text: str, total_match) -> dict:
    summary = re.search(
        r"Summary\s*:\s*([0-9]+) OK, ([0-9]+) broken, ([0-9]+) redirecting off-host, "
        r"([0-9]+) blocked",
        text,
    )
    if not summary:
        return {}
    return {
        "ok": int(summary.group(1)),
        "broken": int(summary.group(2)),
        "moved": int(summary.group(3)),
        "blocked": int(summary.group(4)),
        "total_links": int(total_match.group(1)) if total_match else 0,
    }


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def backfill(
    *,
    check_classes: tuple,
    broken_classes: set[str],
    report_dir: str = "link_reports",
    page_names: tuple = GENERATED_PAGE_NAMES,
    backups_dir: str = "local_backups",
    db_path: str = history.DB_PATH,
    verbose: bool = True,
) -> dict:
    """Record every build and link check recoverable from disk and git."""
    def say(msg: str):
        if verbose:
            print(msg)

    builds = 0
    skipped = 0
    unparseable = 0

    candidates: list[tuple[str, str]] = []

    for name in page_names:
        p = Path(name)
        if p.exists():
            candidates.append((str(p), p.read_text(encoding="utf-8", errors="replace")))

    backups = Path(backups_dir)
    if backups.is_dir():
        for p in sorted(backups.glob("*.html")):
            candidates.append((str(p), p.read_text(encoding="utf-8", errors="replace")))

    candidates.extend(committed_pages())

    parsed_pages: list[tuple[str, dict]] = []
    for label, html in candidates:
        parsed = parse_built_page(html)
        if not parsed:
            unparseable += 1
            continue
        parsed_pages.append((label, parsed))

    for label, parsed in sorted(parsed_pages, key=lambda pair: pair[1]["ran_at"]):
        if _record_page(parsed, label, db_path):
            builds += 1
            say(f"  build  {parsed['ran_at']}  {len(parsed['sites']):>4} sites  {label}")
        else:
            skipped += 1

    # Link reports: pair each .txt with the .csv written beside it.
    class_headings = {
        heading.split("—")[0].strip(): klass for klass, heading in check_classes
    }
    checks = 0
    checks_skipped = 0
    reports = Path(report_dir)
    if reports.is_dir():
        for txt in sorted(reports.glob("*.txt")):
            parsed = parse_link_report(txt, txt.with_suffix(".csv"), class_headings)
            if not parsed:
                continue
            if history.run_exists("link_runs", parsed["ran_at"], db_path):
                checks_skipped += 1
                continue
            if parsed["results"]:
                history.record_link_check(
                    results=parsed["results"],
                    broken_classes=broken_classes,
                    source_csv=parsed["source_csv"],
                    ran_at=parsed["ran_at"],
                    reconstructed=True,
                    note="Reconstructed from the report files this check wrote.",
                    db_path=db_path,
                )
            else:
                t = parsed["totals"] or {}
                if not t:
                    continue
                with history.connect(db_path) as conn:
                    conn.execute(
                        """INSERT INTO link_runs (ran_at, source_csv, total_links,
                               ok, broken, moved, blocked, reconstructed, note)
                           VALUES (?,?,?,?,?,?,?,1,?)""",
                        (parsed["ran_at"], parsed["source_csv"], t.get("total_links", 0),
                         t.get("ok", 0), t.get("broken", 0), t.get("moved", 0),
                         t.get("blocked", 0),
                         "Totals only — no per-site CSV was found beside the text report."),
                    )
            checks += 1
            say(f"  check  {parsed['ran_at']}  {len(parsed['results']):>4} links  {txt.name}")

    return {
        "builds": builds,
        "builds_already_present": skipped,
        "pages_unparseable": unparseable,
        "checks": checks,
        "checks_already_present": checks_skipped,
    }
