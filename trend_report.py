"""
Render the run history as a self-contained HTML report.

The generated page is one file with no external requests — same constraint as
the student-facing page, for the same reason: it has to be openable from an
email attachment or a file share on a network that may not reach the internet.

What it shows, and why in that form:

- The current site count as a hero figure. It is the number the report exists to
  answer, and a number is the right form for one number.
- Growth as a single-series line, broken where the page's *scope* changed. The
  IncarEducation filter arrived on 2026-09-16 and cut the page from 137 sites to
  103. Drawing one continuous line through that would report a definitional
  change as a 34-site loss, so the pre-filter runs are drawn separately and in
  the de-emphasis gray: context, not the same series.
- Categories as a table, not a chart. There are thirteen of them, which is past
  the point where colour classes stay tellable apart.
- Link health as stat tiles plus a single "needs attention" line. A four-way
  stacked bar was the obvious first idea and the wrong one: "blocked to
  automation" is explicitly not breakage in this codebase, so giving it equal
  visual weight to a dead domain would overstate the problem.
"""

import json
import math
from datetime import datetime
from pathlib import Path

import history

TEMPLATE = "trend_template.html"
OUTPUT = "Build_History.html"

# Chart geometry, in viewBox units.
VB_W, VB_H = 760, 300
PAD_L, PAD_R, PAD_T, PAD_B = 48, 26, 18, 42


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def esc(s) -> str:
    """Escape for HTML text. Quotes included, so the same helper is safe in attributes."""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def parse_stamp(s: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return datetime.strptime(s[:10], "%Y-%m-%d")


def short_date(s: str) -> str:
    return parse_stamp(s).strftime("%-d %b %Y")


def long_stamp(s: str) -> str:
    return parse_stamp(s).strftime("%-d %b %Y, %H:%M")


def signed(n: int) -> str:
    return f"+{n}" if n > 0 else (str(n) if n < 0 else "0")


def delta_class(n: int) -> str:
    return "up" if n > 0 else ("down" if n < 0 else "flat")


def nice_ticks(vmax: float, target: int = 4) -> list[int]:
    """
    Round axis ticks from 0 up to just past vmax: 0 / 50 / 100 / 150 rather than
    0 / 34 / 68, and without overshooting to 400 for a maximum of 137.
    """
    if vmax <= 0:
        return [0, 1]
    raw = vmax / target
    magnitude = 10 ** math.floor(math.log10(raw))
    step = next(
        (m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= raw),
        10 * magnitude,
    )
    # Everything plotted here is a count of sites or links, so a step below 1
    # would otherwise produce a repeated axis like 0 / 0 / 0 / 1 / 1.
    step = max(1, round(step))
    top = math.ceil(vmax / step) * step
    return [step * i for i in range(top // step + 1)]


# ---------------------------------------------------------------------------
# Line chart
# ---------------------------------------------------------------------------
def line_chart(
    rows: list[dict],
    *,
    value_key: str,
    unit: str,
    chart_id: str,
    caption: str,
    group_key=None,
    group_styles: dict | None = None,
    boundary_label: str = "",
) -> str:
    """
    One figure: a zero-based single-series line over real time.

    `group_key(row)` splits the runs into consecutive groups drawn as separate
    polylines — used to break the line where the page's scope changed rather
    than implying continuity across it. Zero-based on purpose: the report is
    about growth, and a truncated axis would overstate every wobble.
    """
    group_styles = group_styles or {}
    times = [parse_stamp(r["ran_at"]) for r in rows]
    values = [r[value_key] for r in rows]
    ticks = nice_ticks(max(values))
    v_max = ticks[-1]

    plot_w = VB_W - PAD_L - PAD_R
    plot_h = VB_H - PAD_T - PAD_B

    # One evenly spaced slot per build, not a calendar axis. Four of these
    # builds ran within three hours of each other and the rest are months
    # apart; on a true time axis the recent ones collapse into a few pixels —
    # which is exactly the part of the series anyone is reading. The dates stay
    # on the axis labels, in the tooltip and in the run table.
    def sx(i: int) -> float:
        if len(rows) == 1:
            return PAD_L + plot_w / 2
        return PAD_L + i * plot_w / (len(rows) - 1)

    def sy(v: float) -> float:
        return PAD_T + plot_h - (v / v_max) * plot_h

    parts: list[str] = []

    # Gridlines: solid hairlines, one step off the surface, recessive.
    for tick in ticks:
        y = sy(tick)
        parts.append(
            f'<line x1="{PAD_L}" y1="{y:.1f}" x2="{PAD_L + plot_w}" y2="{y:.1f}" '
            f'stroke="var(--gridline)" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{PAD_L - 9}" y="{y + 4:.1f}" text-anchor="end" font-size="11" '
            f'fill="var(--text-muted)" style="font-variant-numeric:tabular-nums">{tick}</text>'
        )

    # Label a handful of slots, always including the first and last. Labelling
    # every build collides as soon as there are more than about eight.
    axis_y = PAD_T + plot_h
    parts.append(
        f'<line x1="{PAD_L}" y1="{axis_y}" x2="{PAD_L + plot_w}" y2="{axis_y}" '
        f'stroke="var(--baseline)" stroke-width="1"/>'
    )
    last = len(rows) - 1
    label_every = max(1, math.ceil(len(rows) / 6))
    label_slots = {i for i in range(0, len(rows), label_every)}
    # Drop a label that would sit right next to the always-labelled last one.
    label_slots = {i for i in label_slots if last - i >= label_every / 2 or i == last}
    label_slots.add(last)
    shown_labels: set[str] = set()
    for i in sorted(label_slots):
        label = times[i].strftime("%-d %b %y")
        # Several builds can share a day. Printing the same date twice on the
        # axis says nothing and reads as a mistake; the exact times are on the
        # tooltip and in the run table.
        if label in shown_labels:
            continue
        shown_labels.add(label)
        x = sx(i)
        anchor = "start" if i == 0 else ("end" if i == last else "middle")
        parts.append(
            f'<text x="{x:.1f}" y="{axis_y + 18}" text-anchor="{anchor}" font-size="11" '
            f'fill="var(--text-muted)">{esc(label)}</text>'
        )

    # Group the runs into consecutive runs of the same scope.
    groups: list[tuple[object, list[int]]] = []
    for i, row in enumerate(rows):
        g = group_key(row) if group_key else None
        if groups and groups[-1][0] == g:
            groups[-1][1].append(i)
        else:
            groups.append((g, [i]))

    # A labelled hairline wherever the scope changes, so the break is explained
    # on the chart rather than only in a footnote.
    for gi in range(1, len(groups)):
        first = groups[gi][1][0]
        x = (sx(first - 1) + sx(first)) / 2
        parts.append(
            f'<line x1="{x:.1f}" y1="{PAD_T}" x2="{x:.1f}" y2="{axis_y}" '
            f'stroke="var(--baseline)" stroke-width="1"/>'
        )
        if boundary_label:
            anchor = "end" if x > PAD_L + plot_w * 0.6 else "start"
            dx = -6 if anchor == "end" else 6
            parts.append(
                f'<text x="{x + dx:.1f}" y="{PAD_T + 11}" text-anchor="{anchor}" '
                f'font-size="10.5" fill="var(--text-muted)">{esc(boundary_label)}</text>'
            )

    points: list[dict] = []
    for g, idxs in groups:
        style = group_styles.get(g, {})
        color = style.get("color", "var(--series-1)")
        coords = [(sx(i), sy(values[i])) for i in idxs]

        if len(coords) > 1:
            d = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
            parts.append(
                f'<polyline points="{d}" fill="none" stroke="{color}" stroke-width="2" '
                f'stroke-linejoin="round" stroke-linecap="round"/>'
            )

        for n, i in enumerate(idxs):
            x, y = coords[n]
            # 2px surface ring, so a dot stays legible where it crosses the line.
            parts.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{color}" '
                f'stroke="var(--surface-1)" stroke-width="2"/>'
            )
            points.append({
                "x": round(x, 1), "y": round(y, 1), "color": color,
                "label": long_stamp(rows[i]["ran_at"]),
                "value": f"{values[i]:,}", "unit": unit,
                "scope": style.get("scope", ""),
            })

    # Direct-label the endpoint only. A number on every point is noise.
    last_x, last_y = sx(len(rows) - 1), sy(values[-1])
    label_anchor = "end"
    label_dx = -9
    parts.append(
        f'<text x="{last_x + label_dx:.1f}" y="{last_y - 10:.1f}" text-anchor="{label_anchor}" '
        f'font-size="13" font-weight="650" fill="var(--text-primary)">{values[-1]:,}</text>'
    )

    # Crosshair + focus halo, driven by the script in the template.
    parts.append(
        f'<line class="crosshair" x1="0" y1="{PAD_T}" x2="0" y2="{axis_y}" '
        f'stroke="var(--baseline)" stroke-width="1" style="opacity:0"/>'
    )
    parts.append(
        '<circle class="focus-dot" cx="-99" cy="-99" r="6" fill="var(--series-1)" '
        'stroke="var(--surface-1)" stroke-width="2" style="opacity:0"/>'
    )

    # Hit targets far bigger than the 8px marks, and focusable for keyboard use.
    for i, p in enumerate(points):
        parts.append(
            f'<circle class="hit" data-i="{i}" cx="{p["x"]}" cy="{p["y"]}" r="14" '
            f'fill="transparent" tabindex="0" role="button" '
            f'aria-label="{esc(p["label"])}: {esc(p["value"])} {esc(unit)}"/>'
        )

    body = "\n        ".join(parts)
    return f"""      <figure data-chart="{esc(chart_id)}">
        <figcaption>{esc(caption)}</figcaption>
        <svg class="chart" viewBox="0 0 {VB_W} {VB_H}" role="img"
             aria-label="{esc(caption)}">
        {body}
        </svg>
        <div class="tooltip" role="status" aria-live="polite">
          <div class="tt-date"></div>
          <div class="tt-row"><span class="tt-val"></span><span class="tt-name"></span></div>
          <div class="tt-scope"></div>
        </div>
        <script type="application/json">{json.dumps(points)}</script>
      </figure>"""


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------
def stat_tiles(runs: list[dict], churn: dict | None) -> str:
    latest = runs[-1]
    prev = runs[-2] if len(runs) > 1 else None
    tiles: list[str] = []

    if prev:
        d = latest["total_sites"] - prev["total_sites"]
        same_scope = prev["category_filter"] == latest["category_filter"]
        note = (
            f"since {long_stamp(prev['ran_at'])}"
            if same_scope
            else f"since {long_stamp(prev['ran_at'])} — different scope"
        )
        tiles.append(_tile("Change since previous build", signed(d), note, delta_class(d)))
    else:
        tiles.append(_tile("Change since previous build", "—", "first recorded build", "flat"))

    tiles.append(_tile("Categories", f"{latest['total_categories']}", "on the current page"))

    if churn:
        tiles.append(_tile(
            "Sites added", f"{len(churn['added'])}",
            f"since {long_stamp(prev['ran_at'])}" if prev else "",
            "up" if churn["added"] else "flat",
        ))
        tiles.append(_tile(
            "Sites removed", f"{len(churn['removed'])}",
            f"since {long_stamp(prev['ran_at'])}" if prev else "",
            "down" if churn["removed"] else "flat",
        ))
    else:
        tiles.append(_tile("Runs recorded", f"{len(runs)}", "builds in the history"))

    return "\n".join(tiles)


def _tile(label: str, value: str, delta: str = "", cls: str = "") -> str:
    delta_html = (
        f'\n          <div class="delta {cls}">{esc(delta)}</div>' if delta else ""
    )
    return (
        f'        <div class="tile">\n'
        f'          <div class="label">{esc(label)}</div>\n'
        f'          <div class="value">{esc(value)}</div>{delta_html}\n'
        f'        </div>'
    )


def category_table(runs: list[dict]) -> str:
    latest = runs[-1]
    cats = latest["categories"]
    prev_cats: dict[str, int] = {}
    prev_comparable = False
    if len(runs) > 1 and runs[-2]["category_filter"] == latest["category_filter"]:
        prev_cats = runs[-2]["categories"]
        prev_comparable = True

    biggest = max(cats.values()) if cats else 1
    rows: list[str] = []
    for cat, n in sorted(cats.items(), key=lambda kv: (-kv[1], kv[0].lower())):
        if prev_comparable:
            d = n - prev_cats.get(cat, 0)
            change = f'<span class="{delta_class(d)}">{signed(d)}</span>' if d else '<span class="flat">—</span>'
        else:
            change = '<span class="flat">n/a</span>'
        pct = n / biggest * 100
        rows.append(
            f'          <tr>\n'
            f'            <td>{esc(cat)}</td>\n'
            f'            <td class="num">{n}</td>\n'
            f'            <td class="num">{change}</td>\n'
            f'            <td style="width:34%"><span class="bar-track">'
            f'<span class="bar-fill" style="width:{pct:.1f}%"></span></span></td>\n'
            f'          </tr>'
        )

    caption = (
        f"Sites per category on the build of {long_stamp(latest['ran_at'])}"
        + (f", and the change since {long_stamp(runs[-2]['ran_at'])}." if prev_comparable
           else ". The previous build used a different scope, so no change is shown.")
    )
    return (
        f'      <table>\n'
        f'        <caption>{esc(caption)}</caption>\n'
        f'        <thead><tr><th>Category</th><th class="num">Sites</th>'
        f'<th class="num">Change</th><th>Share</th></tr></thead>\n'
        f'        <tbody>\n' + "\n".join(rows) + '\n        </tbody>\n      </table>'
    )


def churn_section(runs: list[dict], churn: dict | None) -> str:
    if not churn or len(runs) < 2:
        return ""
    prev, latest = runs[-2], runs[-1]
    added, removed, recat = churn["added"], churn["removed"], churn["recategorized"]
    if not (added or removed or recat):
        body = (
            '      <p class="empty">No site was added or removed between these two builds.</p>'
        )
        if latest["total_sites"] != prev["total_sites"]:
            body += (
                f'\n      <p class="empty">The published total still moved from '
                f'{prev["total_sites"]} to {latest["total_sites"]}, because the difference was '
                f'the same site listed more than once rather than a site arriving or leaving.</p>'
            )
    else:
        body = _churn_list("Added", added) + _churn_list("Removed", removed)
        if recat:
            items = "".join(
                f'          <li>{esc(s["name"])} — {esc(s["was"])} &rarr; {esc(s["now"])}</li>\n'
                for s in recat
            )
            body += (
                f'      <p style="margin:16px 0 4px"><strong>Re-categorised '
                f'({len(recat)})</strong></p>\n        <ul>\n{items}        </ul>\n'
            )

    return f"""  <section aria-label="What changed">
    <h2>What changed</h2>
    <p class="section-note">Between the build of {esc(long_stamp(prev['ran_at']))} and
      {esc(long_stamp(latest['ran_at']))}. Sites are matched by address, ignoring
      <code>www.</code>, scheme and trailing slashes, so a site whose listed address was
      merely respelled between exports does not read as one removal plus one addition.</p>
    <div class="card">
{body}
    </div>
  </section>
"""


def _churn_list(heading: str, sites: list[dict]) -> str:
    if not sites:
        return f'      <p class="empty"><strong>{heading} (0)</strong></p>\n'
    shown = sites[:15]
    items = "".join(
        f'          <li>{esc(s["name"])} <span class="pill">{esc(s["category"])}</span>'
        f'<br><span class="url">{esc(s["url"])}</span></li>\n'
        for s in shown
    )
    more = ""
    if len(sites) > len(shown):
        rest = "".join(
            f'          <li>{esc(s["name"])} <span class="pill">{esc(s["category"])}</span>'
            f'<br><span class="url">{esc(s["url"])}</span></li>\n'
            for s in sites[len(shown):]
        )
        more = (
            f'      <details class="more"><summary>and {len(sites) - len(shown)} more</summary>\n'
            f'        <ul>\n{rest}        </ul>\n      </details>\n'
        )
    return (
        f'      <p style="margin:0 0 4px"><strong>{heading} ({len(sites)})</strong></p>\n'
        f'      <ul>\n{items}      </ul>\n{more}'
    )


def link_section(link_runs: list[dict], problems: list[dict]) -> str:
    if not link_runs:
        return """  <section aria-label="Link health">
    <h2>Link health</h2>
    <p class="section-note">No link check has been recorded yet. Run
      <code>python build_approved_sites.py --check-links</code> and it will appear here.</p>
  </section>
"""
    latest = link_runs[-1]
    attention = latest["broken"] + latest["moved"]

    tiles = "\n".join([
        _tile("Working", f"{latest['ok']}", "reachable as listed", "up"),
        _tile("Broken", f"{latest['broken']}", "a student hits a dead link",
              "down" if latest["broken"] else "flat"),
        _tile("Redirecting off-host", f"{latest['moved']}", "may need whitelisting",
              "down" if latest["moved"] else "flat"),
        _tile("Blocked to automation", f"{latest['blocked']}", "not breakage — verify by hand"),
    ])

    chart = ""
    if len(link_runs) > 1:
        rows = [dict(r, attention=r["broken"] + r["moved"]) for r in link_runs]
        chart = (
            '    <div class="card chart-card" style="margin-top:14px">\n'
            + line_chart(
                rows,
                value_key="attention",
                unit="links needing attention",
                chart_id="link-health",
                caption="Links needing attention (broken, plus redirecting off-host) per check",
                group_styles={None: {"color": "var(--critical)"}},
            )
            + "\n    </div>"
        )
    else:
        chart = (
            '    <p class="section-note" style="margin-top:12px">A trend line appears here '
            'once a second check has been recorded.</p>'
        )

    problem_table = ""
    if problems:
        rows = "".join(
            f'          <tr>\n'
            f'            <td class="wrap-cell">{esc(p["name"])}'
            f'<br><span class="url">{esc(p["url"])}</span></td>\n'
            f'            <td>{esc(p["klass"].replace("_", " "))}</td>\n'
            f'            <td class="wrap-cell">{esc(p["detail"])}</td>\n'
            f'            <td>{esc(short_date(p["since"]))}</td>\n'
            f'            <td class="num">{p["runs_affected"]}</td>\n'
            f'          </tr>\n'
            for p in problems
        )
        problem_table = f"""    <div class="card table-wrap" style="margin-top:14px">
      <table>
        <caption>Every link flagged by the most recent check, with how long it has been
          flagged without interruption.</caption>
        <thead><tr><th>Site</th><th>Finding</th><th>Detail</th><th>Flagged since</th>
          <th class="num">Checks</th></tr></thead>
        <tbody>
{rows}        </tbody>
      </table>
    </div>"""

    return f"""  <section aria-label="Link health">
    <h2>Link health</h2>
    <p class="section-note">From the check of {esc(long_stamp(latest['ran_at']))}, which tested
      {latest['total_links']} links and found {attention} needing attention. Checked from a staff
      network, not from inside a facility.</p>
    <div class="tiles" style="grid-template-columns:repeat(auto-fit,minmax(150px,1fr))">
{tiles}
    </div>
{chart}
{problem_table}
  </section>
"""


def run_table(runs: list[dict], link_runs: list[dict]) -> str:
    rows: list[str] = []
    for i, r in enumerate(runs):
        prev = runs[i - 1] if i else None
        d = r["total_sites"] - prev["total_sites"] if prev else None
        change = (
            f'<span class="{delta_class(d)}">{signed(d)}</span>' if d is not None and d
            else ('<span class="flat">—</span>' if d is not None else "")
        )
        distinct = (
            f'{r["distinct_sites"]}' if r["distinct_sites"] != r["total_sites"] else ""
        )
        flags = []
        if r["reconstructed"]:
            flags.append('<span class="pill">reconstructed</span>')
        scope = r["category_filter"] or "full whitelist"
        rows.append(
            f'          <tr>\n'
            f'            <td>{esc(long_stamp(r["ran_at"]))}</td>\n'
            f'            <td class="num">{r["total_sites"]}</td>\n'
            f'            <td class="num">{change}</td>\n'
            f'            <td class="num">{distinct}</td>\n'
            f'            <td class="num">{r["total_categories"]}</td>\n'
            f'            <td>{esc(scope)}</td>\n'
            f'            <td class="wrap-cell">{esc(r["source_csv"] or r["output_file"] or "")}'
            f' {"".join(flags)}</td>\n'
            f'          </tr>'
        )

    link_rows = "".join(
        f'          <tr>\n'
        f'            <td>{esc(long_stamp(r["ran_at"]))}</td>\n'
        f'            <td class="num">{r["total_links"]}</td>\n'
        f'            <td class="num">{r["ok"]}</td>\n'
        f'            <td class="num">{r["broken"]}</td>\n'
        f'            <td class="num">{r["moved"]}</td>\n'
        f'            <td class="num">{r["blocked"]}</td>\n'
        f'          </tr>\n'
        for r in link_runs
    )
    link_block = ""
    if link_rows:
        link_block = f"""
      <table style="margin-top:26px">
        <caption>Link checks.</caption>
        <thead><tr><th>Checked</th><th class="num">Links</th><th class="num">Working</th>
          <th class="num">Broken</th><th class="num">Off-host</th>
          <th class="num">Blocked</th></tr></thead>
        <tbody>
{link_rows}        </tbody>
      </table>"""

    return (
        f'      <table>\n'
        f'        <caption>Builds. &ldquo;Distinct&rdquo; is filled in only where it differs from '
        f'the published total.</caption>\n'
        f'        <thead><tr><th>Built</th><th class="num">Sites</th><th class="num">Change</th>'
        f'<th class="num">Distinct</th><th class="num">Categories</th><th>Scope</th>'
        f'<th>Source</th></tr></thead>\n'
        f'        <tbody>\n' + "\n".join(rows) + '\n        </tbody>\n      </table>'
        + link_block
    )


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------
def render(
    *,
    broken_classes: set[str],
    db_path: str = history.DB_PATH,
    template: str = TEMPLATE,
    output: str = OUTPUT,
) -> dict:
    """Write the trend report. Returns a small summary for the console."""
    runs = history.build_runs(db_path)
    if not runs:
        raise SystemExit(
            "No build history recorded yet, so there is nothing to report.\n"
            "Run a build, or seed the history from past builds with:\n"
            "  python build_approved_sites.py --backfill-history"
        )

    link_runs = history.link_run_history(db_path)
    problems = history.standing_problems(broken_classes, db_path)

    latest = runs[-1]
    prev = runs[-2] if len(runs) > 1 else None
    churn = history.churn(prev["id"], latest["id"], db_path) if prev else None

    # Runs in the current scope, for an honest "growth" figure.
    scope = latest["category_filter"]
    same_scope = [r for r in runs if r["category_filter"] == scope]
    if len(same_scope) > 1:
        growth = latest["total_sites"] - same_scope[0]["total_sites"]
        growth_line = (
            f"{signed(growth)} sites since {long_stamp(same_scope[0]['ran_at'])}, "
            f"across {len(same_scope)} builds on the current scope."
        )
    else:
        growth_line = "This is the first build recorded on the current scope."

    hero_delta = ""
    if prev:
        d = latest["total_sites"] - prev["total_sites"]
        hero_delta = f"{signed(d)} since the build of {long_stamp(prev['ran_at'])}"
    else:
        hero_delta = "first recorded build"

    scope_label = "education rows only" if scope else "the full approved whitelist"
    boundary = "IncarEducation filter added" if any(
        r["category_filter"] != runs[0]["category_filter"] for r in runs
    ) else ""

    chart = line_chart(
        runs,
        value_key="total_sites",
        unit="sites on the page",
        chart_id="growth",
        caption="Sites published per build. The axis starts at zero, and the line breaks "
                "where the page's scope changed.",
        group_key=lambda r: r["category_filter"],
        group_styles={
            scope: {"color": "var(--series-1)", "scope": f"Scope: {scope_label}"},
            "": {"color": "var(--deemphasis)", "scope": "Scope: full approved whitelist"},
        },
        boundary_label=boundary,
    )

    legend = ""
    if len({r["category_filter"] for r in runs}) > 1:
        legend = """
      <ul class="legend">
        <li><span class="key" style="background:var(--series-1)"></span> Education only (current scope)</li>
        <li><span class="key" style="background:var(--deemphasis)"></span> Full approved whitelist (earlier scope)</li>
      </ul>"""

    notes: list[str] = []
    if any(r["reconstructed"] for r in runs):
        n = sum(1 for r in runs if r["reconstructed"])
        notes.append(
            f"{n} of {len(runs)} builds are marked <span class=\"pill\">reconstructed</span>. "
            "Their counts were read back from pages those builds generated — committed copies "
            "and local backups — rather than measured while the build ran. The numbers are the "
            "builds' own; only the manner of recording differs."
        )
    if boundary:
        notes.append(
            "The page's scope changed on 16 Sep 2026, when it began building only rows DOC tags "
            "<code>IncarEducation</code>. Earlier builds covered the whole approved whitelist, so "
            "the drop from 137 to 103 sites is a narrowing of scope, not sites being withdrawn. "
            "The line is broken there for that reason, and totals either side are not comparable."
        )
    for r in runs:
        if r["note"] and "distinct addresses" in r["note"]:
            notes.append(
                "Some earlier builds published the same site twice under two spellings of its "
                "address. Where that happened the run table shows a lower &ldquo;distinct&rdquo; "
                "count beside the published total."
            )
            break
    if link_runs:
        notes.append(
            "Link checks run from a staff network, not from inside a facility. A site reachable "
            "here can still be blocked by the facility filter, and an internal-only host can fail "
            "here yet work there. <em>Blocked to automation</em> is counted separately from broken "
            "for that reason — those hosts answered, they just refuse automated requests."
        )
    notes.append(
        "Every figure in the charts is also in the tables, so nothing here depends on hovering."
    )
    notes_html = "\n".join(f"      <li>{n}</li>" for n in notes)

    html = Path(template).read_text(encoding="utf-8")
    replacements = {
        "{{SCOPE_LINE}}": esc(
            f"{len(runs)} builds recorded, {short_date(runs[0]['ran_at'])} to "
            f"{short_date(latest['ran_at'])}. Current scope: {scope_label}."
        ),
        "{{HERO_LABEL}}": "Approved sites on the current page",
        "{{HERO_VALUE}}": f"{latest['total_sites']:,}",
        "{{HERO_META}}": esc(hero_delta),
        "{{STAT_TILES}}": stat_tiles(runs, churn),
        "{{GROWTH_NOTE}}": esc(growth_line),
        "{{GROWTH_CHART}}": chart + legend,
        "{{CATEGORY_NOTE}}": esc(
            "Thirteen categories is past the point where colours stay tellable apart, "
            "so this is a table."
        ),
        "{{CATEGORY_TABLE}}": category_table(runs),
        "{{CHURN_SECTION}}": churn_section(runs, churn),
        "{{LINK_SECTION}}": link_section(link_runs, problems),
        "{{RUN_NOTE}}": esc(
            "The full record behind the charts above — the table view of everything plotted."
        ),
        "{{RUN_TABLE}}": run_table(runs, link_runs),
        "{{NOTES}}": notes_html,
        "{{GENERATED}}": esc(datetime.now().strftime("%-d %b %Y, %H:%M")),
        "{{DB_PATH}}": esc(db_path),
    }
    for key, value in replacements.items():
        if key not in html:
            print(f"Warning: placeholder {key} not found in {template}.")
        html = html.replace(key, value)

    Path(output).write_text(html, encoding="utf-8")
    return {
        "output": output,
        "builds": len(runs),
        "link_checks": len(link_runs),
        "latest_total": latest["total_sites"],
        "problems": len(problems),
    }
