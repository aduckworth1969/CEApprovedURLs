"""
Run history for the approved sites page.

Every build and every --check-links run is recorded in a small SQLite database
(data/build_history.db), so counts that used to exist only in one run's console
output become a series you can chart. That answers the question the page itself
cannot: not "how many sites are approved today" but "how is that changing".

Why SQLite: it is in the standard library, it is a single file that can be
copied or backed up like any other, and it survives the generator being
rewritten. Nothing here needs a server.

Two kinds of run are recorded, in parallel sets of tables:

  build_runs   + build_run_categories + build_run_sites
  link_runs    + link_findings

Per-run *site lists* are stored, not just totals. They cost a few kilobytes per
run and they are what makes the interesting questions answerable: which sites
appeared or disappeared between two runs, and how long a given link has been
broken. A totals-only table cannot answer either.

Runs reconstructed from files on disk rather than observed live are flagged
`reconstructed = 1`, so a chart can say so rather than implying the same
confidence as a measured run.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from urlkeys import url_key

DB_PATH = "data/build_history.db"

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS build_runs (
    id                    INTEGER PRIMARY KEY,
    ran_at                TEXT    NOT NULL,
    source_csv            TEXT    DEFAULT '',
    output_file           TEXT    DEFAULT '',
    category_filter       TEXT    DEFAULT '',
    export_rows           INTEGER,
    rows_skipped_category INTEGER,
    total_sites           INTEGER NOT NULL,
    distinct_sites        INTEGER NOT NULL,
    total_categories      INTEGER NOT NULL,
    duplicates_collapsed  INTEGER DEFAULT 0,
    removed_by_override   INTEGER DEFAULT 0,
    replaced_by_override  INTEGER DEFAULT 0,
    descriptions_scraped  INTEGER DEFAULT 0,
    descriptions_cached   INTEGER DEFAULT 0,
    reconstructed         INTEGER DEFAULT 0,
    note                  TEXT    DEFAULT ''
);

CREATE TABLE IF NOT EXISTS build_run_categories (
    run_id     INTEGER NOT NULL REFERENCES build_runs(id) ON DELETE CASCADE,
    category   TEXT    NOT NULL,
    site_count INTEGER NOT NULL,
    PRIMARY KEY (run_id, category)
);

CREATE TABLE IF NOT EXISTS build_run_sites (
    run_id   INTEGER NOT NULL REFERENCES build_runs(id) ON DELETE CASCADE,
    url_key  TEXT    NOT NULL,
    name     TEXT    NOT NULL,
    url      TEXT    NOT NULL,
    category TEXT    NOT NULL,
    PRIMARY KEY (run_id, url_key)
);

CREATE TABLE IF NOT EXISTS link_runs (
    id            INTEGER PRIMARY KEY,
    ran_at        TEXT    NOT NULL,
    source_csv    TEXT    DEFAULT '',
    total_links   INTEGER NOT NULL,
    ok            INTEGER DEFAULT 0,
    broken        INTEGER DEFAULT 0,
    moved         INTEGER DEFAULT 0,
    blocked       INTEGER DEFAULT 0,
    reconstructed INTEGER DEFAULT 0,
    note          TEXT    DEFAULT ''
);

CREATE TABLE IF NOT EXISTS link_findings (
    run_id  INTEGER NOT NULL REFERENCES link_runs(id) ON DELETE CASCADE,
    url_key TEXT    NOT NULL,
    name    TEXT    NOT NULL,
    url     TEXT    NOT NULL,
    klass   TEXT    NOT NULL,
    detail  TEXT    DEFAULT '',
    suggest TEXT    DEFAULT '',
    PRIMARY KEY (run_id, url_key)
);

CREATE INDEX IF NOT EXISTS build_runs_ran_at   ON build_runs(ran_at);
CREATE INDEX IF NOT EXISTS link_runs_ran_at    ON link_runs(ran_at);
CREATE INDEX IF NOT EXISTS link_findings_klass ON link_findings(klass);
"""


@contextmanager
def connect(db_path: str = DB_PATH):
    """
    Open the history database, creating and migrating it if needed.

    Foreign keys are enabled per-connection (SQLite defaults them off), so
    deleting a run really does take its child rows with it.
    """
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(_SCHEMA)
        if conn.execute("PRAGMA user_version").fetchone()[0] < SCHEMA_VERSION:
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()
        yield conn
        conn.commit()
    finally:
        conn.close()


def _stamp(when: datetime | str | None) -> str:
    if when is None:
        when = datetime.now()
    if isinstance(when, datetime):
        return when.strftime("%Y-%m-%d %H:%M:%S")
    return str(when)


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------
def record_build(
    *,
    sites: list[tuple[str, str, str]],
    counts: dict,
    source_csv: str = "",
    output_file: str = "",
    category_filter: str = "",
    ran_at=None,
    reconstructed: bool = False,
    note: str = "",
    db_path: str = DB_PATH,
) -> int:
    """
    Record one build. `sites` is (name, url, category) for every site that made
    it onto the page; `counts` carries the build's own tallies (see the keys
    read below). Returns the new run's id.
    """
    stamp = _stamp(ran_at)
    by_category: dict[str, int] = {}
    for _, _, category in sites:
        by_category[category] = by_category.get(category, 0) + 1

    # Two counts, because they can legitimately differ. `total_sites` is what
    # the page published — the number of tiles a student saw. `distinct_sites`
    # is how many separate addresses that was. A live build collapses spelling
    # duplicates before it gets here so the two agree, but pages generated
    # before that collapsing existed really did list one site twice, and
    # flattening the difference would either overstate the site table or
    # understate the page.
    deduped: dict[str, tuple[str, str, str]] = {}
    for name, url, category in sites:
        deduped.setdefault(url_key(url), (name, url, category))

    with connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO build_runs (
                ran_at, source_csv, output_file, category_filter,
                export_rows, rows_skipped_category,
                total_sites, distinct_sites, total_categories,
                duplicates_collapsed, removed_by_override, replaced_by_override,
                descriptions_scraped, descriptions_cached,
                reconstructed, note
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                stamp, source_csv, output_file, category_filter,
                counts.get("export_rows"), counts.get("rows_skipped_category"),
                len(sites), len(deduped), len(by_category),
                counts.get("duplicates_collapsed", 0),
                counts.get("removed_by_override", 0),
                counts.get("replaced_by_override", 0),
                counts.get("descriptions_scraped", 0),
                counts.get("descriptions_cached", 0),
                1 if reconstructed else 0, note,
            ),
        )
        run_id = cur.lastrowid

        conn.executemany(
            "INSERT INTO build_run_categories (run_id, category, site_count) VALUES (?,?,?)",
            [(run_id, cat, n) for cat, n in sorted(by_category.items())],
        )
        conn.executemany(
            """INSERT INTO build_run_sites (run_id, url_key, name, url, category)
               VALUES (?,?,?,?,?)""",
            [(run_id, key, name, url, cat) for key, (name, url, cat) in deduped.items()],
        )
    return run_id


def record_link_check(
    *,
    results: list[dict],
    broken_classes: set[str],
    source_csv: str = "",
    ran_at=None,
    reconstructed: bool = False,
    note: str = "",
    db_path: str = DB_PATH,
) -> int:
    """
    Record one --check-links run. `results` is the checker's own result dicts;
    `broken_classes` is its CHECK_BROKEN set, passed in rather than imported so
    this module stays independent of the builder.
    """
    stamp = _stamp(ran_at)
    broken = sum(1 for r in results if r.get("klass") in broken_classes)
    moved = sum(1 for r in results if r.get("klass") == "moved")
    blocked = sum(1 for r in results if r.get("klass") == "blocked")
    ok = len(results) - broken - moved - blocked

    with connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO link_runs (
                ran_at, source_csv, total_links, ok, broken, moved, blocked,
                reconstructed, note
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (stamp, source_csv, len(results), ok, broken, moved, blocked,
             1 if reconstructed else 0, note),
        )
        run_id = cur.lastrowid
        conn.executemany(
            """INSERT OR IGNORE INTO link_findings
               (run_id, url_key, name, url, klass, detail, suggest)
               VALUES (?,?,?,?,?,?,?)""",
            [
                (run_id, url_key(r.get("url", "")), r.get("name", ""),
                 r.get("url", ""), r.get("klass", ""), r.get("detail", "") or "",
                 r.get("suggest", "") or "")
                for r in results
            ],
        )
    return run_id


def run_exists(table: str, ran_at, db_path: str = DB_PATH) -> bool:
    """Whether a run is already recorded at this timestamp. Keeps backfill idempotent."""
    if table not in ("build_runs", "link_runs"):
        raise ValueError(f"unknown table: {table}")
    with connect(db_path) as conn:
        row = conn.execute(
            f"SELECT 1 FROM {table} WHERE ran_at = ? LIMIT 1", (_stamp(ran_at),)
        ).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------
def build_runs(db_path: str = DB_PATH) -> list[dict]:
    """Every build run, oldest first, each with its category breakdown attached."""
    with connect(db_path) as conn:
        runs = [dict(r) for r in conn.execute(
            "SELECT * FROM build_runs ORDER BY ran_at, id"
        )]
        by_run: dict[int, dict[str, int]] = {}
        for row in conn.execute(
            "SELECT run_id, category, site_count FROM build_run_categories"
        ):
            by_run.setdefault(row["run_id"], {})[row["category"]] = row["site_count"]
    for r in runs:
        r["categories"] = by_run.get(r["id"], {})
    return runs


def link_run_history(db_path: str = DB_PATH) -> list[dict]:
    """Every link-check run, oldest first."""
    with connect(db_path) as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM link_runs ORDER BY ran_at, id"
        )]


def sites_for_run(run_id: int, db_path: str = DB_PATH) -> dict[str, dict]:
    """The sites on one build, keyed by url_key."""
    with connect(db_path) as conn:
        return {
            r["url_key"]: dict(r)
            for r in conn.execute(
                "SELECT * FROM build_run_sites WHERE run_id = ? ORDER BY name", (run_id,)
            )
        }


def churn(previous_run_id: int, run_id: int, db_path: str = DB_PATH) -> dict:
    """
    What changed between two builds: sites added, removed, and re-categorized.

    Matching is by url_key, so a site whose listed address gained a www or lost
    a trailing slash between exports reads as the same site rather than as one
    removal plus one addition.
    """
    before = sites_for_run(previous_run_id, db_path)
    after = sites_for_run(run_id, db_path)

    added = [after[k] for k in after.keys() - before.keys()]
    removed = [before[k] for k in before.keys() - after.keys()]
    recategorized = [
        {"name": after[k]["name"], "url": after[k]["url"],
         "was": before[k]["category"], "now": after[k]["category"]}
        for k in after.keys() & before.keys()
        if before[k]["category"] != after[k]["category"]
    ]
    return {
        "added": sorted(added, key=lambda s: s["name"].lower()),
        "removed": sorted(removed, key=lambda s: s["name"].lower()),
        "recategorized": sorted(recategorized, key=lambda s: s["name"].lower()),
    }


def standing_problems(broken_classes: set[str], db_path: str = DB_PATH) -> list[dict]:
    """
    Links that were a problem in the most recent check, with the date they first
    became one *in an unbroken streak* — so a site that broke, was fixed, and
    broke again reports the latest streak rather than the original date.

    This is the question the timestamped report files could only answer by
    someone opening several of them side by side.
    """
    with connect(db_path) as conn:
        runs = [dict(r) for r in conn.execute(
            "SELECT id, ran_at FROM link_runs ORDER BY ran_at, id"
        )]
        if not runs:
            return []
        latest = runs[-1]

        findings: dict[int, dict[str, dict]] = {}
        for row in conn.execute(
            "SELECT run_id, url_key, name, url, klass, detail, suggest FROM link_findings"
        ):
            findings.setdefault(row["run_id"], {})[row["url_key"]] = dict(row)

    interesting = broken_classes | {"moved"}
    out = []
    for key, row in findings.get(latest["id"], {}).items():
        if row["klass"] not in interesting:
            continue
        since = latest["ran_at"]
        streak = 1
        # Walk back while this link was a problem in every consecutive run that
        # actually checked it. A run that did not include the site at all ends
        # the streak: absence is not evidence it was working.
        for run in reversed(runs[:-1]):
            prior = findings.get(run["id"], {}).get(key)
            if prior is None or prior["klass"] not in interesting:
                break
            since = run["ran_at"]
            streak += 1
        out.append({**row, "since": since, "runs_affected": streak})
    return sorted(out, key=lambda r: (r["since"], r["name"].lower()))
