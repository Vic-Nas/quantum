"""Build a multi-page static site: home countdown, per-threat detail pages,
a research index, hardware roadmaps, and a full technical chart."""
import hashlib
import html
import json
import math
import os
import re
import shutil
import sys
from pathlib import Path

from . import cardimg, cards, chart
from .breakdate import METRICS, earliest_path, pos, requirement, supply_points
from .present import (GLOSSARY, datetime_label, ALGORITHMS, ALGORITHMS_NOTE, CHART_GROUPS, CONSEQUENCE, COUNTDOWN,
                      PROXY_TARGETS, SECURES, SECURES_NOTE, SERVICES, clean, count,
                      date_label, dom_id, duration, headline, label, paper_id,
                      paper_rows, pct_label, plain_reason, series, short_count, strip_dashes, year_frac,
                      year_label)

WEB = Path("web")
DEFAULT_URL = "https://vic-nas.github.io/quantum/"
REPO_URL = "https://github.com/Vic-Nas/quantum"
NAV = [("", "Home"), ("research/", "Research"), ("hardware/", "Hardware"), ("chart/", "Chart")]


def base_url() -> str:
    url = (os.environ.get("QTD_SITE_URL") or "").strip() or DEFAULT_URL
    return url if url.endswith("/") else url + "/"


def e(x) -> str:
    return html.escape(str(x if x is not None else ""), quote=True)


def _root(depth):
    return "../" * depth if depth else ""


def _words(metric):
    return "physical" if metric.startswith("phys") else "logical"


def page_slug(title):
    short = title.split(" and ")[0].split(",")[0].strip().lower()
    return re.sub(r"[^a-z0-9]+", "-", short).strip("-")


# ---------------------------------------------------------------------------
# Asset versioning
# ---------------------------------------------------------------------------

class Assets:
    def __init__(self):
        self._map = {}

    def add(self, rel, body):
        h = hashlib.sha256(body).hexdigest()[:10]
        self._map[rel] = f"assets/{rel}?v={h}"

    def css(self, rels, depth):
        root = _root(depth)
        return [f"{root}{self._map[r]}" for r in rels]


# ---------------------------------------------------------------------------
# Head, nav, shell
# ---------------------------------------------------------------------------

def head(card, css_hrefs, root=""):
    t = [f"<title>{e(card['title'])}</title>",
         f'<meta name="description" content="{e(card["description"])}">',
         f'<meta property="og:site_name" content="{e(card["site_name"])}">',
         f'<meta property="og:type" content="{e(card["type"])}">',
         f'<meta property="og:title" content="{e(card["title"])}">',
         f'<meta property="og:description" content="{e(card["description"])}">',
         f'<meta property="og:url" content="{e(card["url"])}">',
         f'<meta name="twitter:card" content="{"summary_large_image" if card.get("image") else "summary"}">',
         f'<meta name="theme-color" content="{e(card["theme_color"])}">',
         f'<link rel="icon" href="{root}assets/favicon.svg" type="image/svg+xml">']
    if card.get("image"):
        t += [f'<meta property="og:image" content="{e(card["image"])}">',
              f'<meta property="og:image:width" content="{card["image_width"]}">',
              f'<meta property="og:image:height" content="{card["image_height"]}">',
              f'<meta property="og:image:alt" content="{e(card["image_alt"])}">']
    t += [f'<link rel="stylesheet" href="{e(h)}">' for h in css_hrefs]
    return "\n".join(t)


def nav_html(active, depth):
    root = _root(depth)
    parts = []
    for href, name in NAV:
        key = href.strip("/")
        act = ' class="active"' if key == active else ""
        parts.append(f'<a{act} href="{root}{href}">{e(name)}</a>')
    return f'<nav class="top-nav">{"".join(parts)}</nav>'


def shell(body, card, assets, css_rels, depth, updated, nav_active=""):
    root = _root(depth)
    css_hrefs = assets.css(css_rels, depth)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
{head(card, css_hrefs, root)}
</head><body>
<header class="app-bar">
<a class="brand" href="{root}"><img src="{root}assets/favicon.svg" alt="" width="22" height="22">Quantum threat tracker</a>
{nav_html(nav_active, depth)}
<span class="bar-end"><span class="upd">Updated {e(updated)}</span>
<a class="gh" href="{e(REPO_URL)}" aria-label="Source code on GitHub" title="Source code on GitHub"><svg viewBox="0 0 16 16" width="20" height="20" aria-hidden="true"><path fill="currentColor" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.6 7.6 0 0 1 4 0c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z"/></svg></a></span>
</header>
<main class="page">{body}</main>
</body></html>"""


def page_card(title, description, page_url):
    return {"site_name": "Quantum threat tracker", "type": "website", "title": title,
            "description": description, "url": page_url, "theme_color": "#c2570c"}


# ---------------------------------------------------------------------------
# Data processing
# ---------------------------------------------------------------------------

def chart_lines(rows, hw_rows, narrow=False):
    out = []
    for target, name, who, status in CHART_GROUPS:
        if not any(r.get("target") == target for r in rows):
            continue
        path = earliest_path(rows, hw_rows, target)
        metric = path.get("metric") or next((m for m in METRICS if requirement(rows, target, m)), None)
        if not metric:
            continue
        need_row = requirement(rows, target, metric)
        year, practical = path.get("year"), status == "broken"
        when_label = year_label(year, path.get("month")) if year else ""
        if not practical:
            when = "not practical"
        elif year:
            when = f"{when_label} or later" if target in PROXY_TARGETS else when_label
        else:
            when = "none announced"
        size = short_count(need_row[metric])
        out.append({"id": dom_id(need_row["id"]), "name": name, "need": need_row[metric], "metric": metric, "year": year,
                    "practical": practical, "when": when, "who": who, "target": target, "row": need_row, "path": path,
                    "due": path.get("when"), "month": path.get("month"), "x": pos(path["supply"]) if path.get("supply") else None,
                    "sub": when if narrow else f"{size} {_words(metric)} · {when}"})
    return out


def countdown_rows(lines):
    by = {ln["target"]: ln for ln in lines}
    out = []
    for title, what, targets in COUNTDOWN:
        mine = [by[t] for t in targets if t in by]
        if not mine:
            continue
        dated = [ln for ln in mine if ln["practical"] and ln["year"]]
        proxy = any(ln["target"] in PROXY_TARGETS for ln in dated)
        first = min(dated, key=lambda ln: ln["due"], default=None)
        out.append({"title": title, "what": what, "id": mine[0]["id"],
                    "year": first["year"] if first else None, "due": first["due"] if first else None,
                    "label": year_label(first["year"], first["month"]) if first else None,
                    "safe": not any(ln["practical"] for ln in mine), "proxy": proxy,
                    "waiting": any(ln["practical"] for ln in mine) and not dated,
                    "lines": mine, "slug": page_slug(title)})
    return out


def radar_rows(path):
    latest = {}
    if not path.exists():
        return []
    for f in sorted(path.glob("*.jsonl")):
        for line in f.read_text().splitlines():
            r = json.loads(line)
            latest[r.get("id") or r.get("url", "")] = r
    def chartable(r):
        ests = r.get("estimates") or []
        return not ests or any(e_["values"].get("physical_qubits") is not None or e_["values"].get("logical_qubits") is not None for e_ in ests)
    return [r for r in latest.values() if r.get("tier") == "B" and chartable(r)][:25]


# ---------------------------------------------------------------------------
# HTML fragments
# ---------------------------------------------------------------------------

def _due(r):
    return r.get("due") or r["year"] + 1.0


def _label(r):
    return r.get("label") or str(r["year"])


def countdown_html(crows, today):
    dues = [_due(r) for r in crows if r["year"]]
    if not dues:
        return ""
    x0, x1 = today, max(dues)
    pct = lambda x: 100 * (x - x0) / (x1 - x0)
    ticks = "".join(f'<span class="yr" style="left:{pct(y + 0.5):.2f}%">{y}</span>'
                    for y in range(int(x0), math.ceil(x1)) if x0 < y + 0.5 <= x1)
    grid = "".join(f'<i class="gl" style="left:{pct(y):.2f}%"></i>'
                   for y in range(int(x0) + 1, math.ceil(x1) + 1) if x0 < y < x1)
    rows_html = []
    for n, r in enumerate(crows):
        href = f"threats/{r['slug']}/"
        if r["safe"]:
            track = '<span class="safe">Safe in practice</span>'
        elif r["year"]:
            end = pct(_due(r))
            track = f'<span class="bar" style="width:{end:.2f}%"><b>{e(_label(r))}{" or later" if r["proxy"] else ""}</b></span>'
        else:
            track = '<span class="safe">No announced machine is big enough yet</span>'
        rows_html.append(
            f'<a class="row{" first" if n == 0 else ""}" href="{href}">'
            f'<span class="who"><strong>{e(r["title"])}</strong><small>{e(r["what"])}</small></span>'
            f'<span class="track">{grid}{track}</span></a>')
    return (f'<section class="cd" aria-label="When it could break"><div class="axis"><span class="who"></span>'
            f'<span class="track">{ticks}</span></div>{"".join(rows_html)}'
            '<p class="foot">Each bar runs from today to the earliest date a vendor has announced a machine big enough. '
            'Plans, not delivered machines.</p></section>')


def threat_grid_html(crows):
    items = []
    for crow in crows:
        if crow["safe"]:
            badge = '<span class="tc-badge safe">Safe in practice</span>'
        elif crow["year"]:
            yr = f'{_label(crow)}{"+" if crow.get("proxy") else ""}'
            badge = f'<span class="tc-badge dated">{e(yr)}</span>'
        else:
            badge = '<span class="tc-badge warn">TBD</span>'
        items.append(
            f'<a class="threat-card" href="threats/{crow["slug"]}/">'
            f'{badge}<h3>{e(crow["title"])}</h3>'
            f'<p>{e(crow["what"])}</p>'
            f'<span class="tc-more">View details</span></a>')
    return f'<div class="card-grid">{"".join(items)}</div>'


def _nice_ticks(lo, hi):
    """Gridline values (1, 2, 5 times a power of ten) between 10**lo and 10**hi."""
    out = []
    for k in range(math.floor(lo), math.ceil(hi) + 1):
        for m in (1, 2, 5):
            v = m * 10 ** k
            if lo <= math.log10(v) <= hi:
                out.append(v)
    return out


def progress_svg(target, rows, metric="physical_qubits", today=None, w=520, h=230):
    """Staircase of the smallest machine each paper says is enough, with the value and the % drop at every record."""
    pts = series(rows, target, metric)
    if len(pts) < 2:
        return ""
    xs = [p["x"] for p in pts]
    ys = [math.log10(max(p["y"], 1)) for p in pts]
    x0, x1 = min(xs) - 0.35, max(max(xs), today or 0) + 0.2
    y0, y1 = min(ys) - 0.35, max(ys) + 0.45
    pl, pr, pt, pb = 58, 14, 14, 28
    pw, ph = w - pl - pr, h - pt - pb

    def sx(v):
        return pl + (v - x0) / (x1 - x0) * pw

    def sy(v):
        return pt + (1 - (math.log10(max(v, 1)) - y0) / (y1 - y0)) * ph

    svg = [f'<svg viewBox="0 0 {w} {h}" class="prog" role="img" aria-label="{e(PROG_META[metric][0])} over time">']
    for v in _nice_ticks(y0, y1):
        yy = sy(v)
        svg.append(f'<line class="g" x1="{pl}" y1="{yy:.1f}" x2="{w - pr}" y2="{yy:.1f}"/>'
                   f'<text class="ax" x="{pl - 8}" y="{yy + 4:.1f}" text-anchor="end">{short_count(v)}</text>')
    span = x1 - x0
    step = 1 if span <= 6 else 2 if span <= 12 else 5
    for yr in range(math.ceil(x0), math.floor(x1) + 1):
        if yr % step == 0 or span <= 6:
            svg.append(f'<text class="ax" x="{sx(yr):.1f}" y="{h - 8}" text-anchor="middle">{yr}</text>')
    recs = [p for p in pts if p["record"]]
    d = []
    for i, p in enumerate(recs):
        px, py = sx(p["x"]), sy(p["y"])
        d.append(f"M{px:.1f},{py:.1f}" if i == 0 else f"H{px:.1f}V{py:.1f}")
    d.append(f"H{sx(max(max(xs), today or 0)):.1f}")
    svg.append(f'<path class="stp" d="{"".join(d)}" fill="none"/>')
    for p in pts:
        px, py = sx(p["x"]), sy(p["y"])
        svg.append(f'<circle class="pt{" rec" if p["record"] else ""}" cx="{px:.1f}" cy="{py:.1f}" r="{5 if p["record"] else 4}">'
                   f'<title>{e(date_label(p["date"]))}: {e(short_count(p["y"]))} {e(_words(metric))} qubits</title></circle>')
    prev_x, prev_below = None, True
    for p in recs:
        px, py = sx(p["x"]), sy(p["y"])
        flip = px > w - pr - 90
        ax, tx = ("end", px - 9) if flip else ("start", px + 9)
        sub = f'down {pct_label(p["drop"])}' if p["drop"] else "first estimate"
        below = prev_x is not None and abs(px - prev_x) < 95 and not prev_below  # a close neighbour took the space above
        v_y, s_y = (py + 18, py + 31) if below else (py - 19, py - 6)
        svg.append(f'<text class="vl" x="{tx:.1f}" y="{v_y:.1f}" text-anchor="{ax}">{short_count(p["y"])}</text>'
                   f'<text class="dl{" dn" if p["drop"] else ""}" x="{tx:.1f}" y="{s_y:.1f}" text-anchor="{ax}">{sub}</text>')
        prev_x, prev_below = px, below
    svg.append("</svg>")
    return "".join(svg)


PROG_META = {"physical_qubits": ("Physical qubits", "The real qubits in a machine."),
             "logical_qubits": ("Logical qubits", "Error-corrected qubits, each made from many physical ones.")}


def progress_cards_html(targets, rows, today):
    cards = []
    for metric in METRICS:
        for t in targets:
            svg = progress_svg(t, rows, metric, today)
            if not svg:
                continue
            svg = (f'<div class="prog-wide">{svg}</div>'
                   f'<div class="prog-narrow">{progress_svg(t, rows, metric, today, w=330, h=240)}</div>')
            pts = series(rows, t, metric)
            first, best = pts[0], min(pts, key=lambda p: (p["y"], -p["x"]))
            foot = f'Best today: <strong>{e(short_count(best["y"]))}</strong>'
            if best is not first:
                foot += f', down {pct_label(1 - best["y"] / first["y"])} since {e(date_label(first["date"], short=True))}'
            title, sub = PROG_META[metric]
            cards.append(f'<div class="prog-card"><h3>{title} needed</h3><p class="dim">{sub}</p>{svg}'
                         f'<p class="prog-foot">{foot}</p></div>')
            break
    if not cards:
        return ""
    return ('<section class="t-section"><h2>How many qubits an attack needs, over time</h2>'
            '<p class="dim">Each dot is a published attack. Lower means an easier attack, so a falling line is bad news.</p>'
            f'<div class="prog-grid">{"".join(cards)}</div></section>')


def stats_html(crow, rows):
    """Three plain facts at the top of a threat page: what it takes today, how that changed, what machines are announced."""
    primary = None
    if not crow["safe"]:
        dated = [ln for ln in crow["lines"] if ln.get("year")]
        primary = min(dated, key=lambda l: l["due"]) if dated else crow["lines"][0]
    else:
        primary = crow["lines"][0]
    metric, row = primary["metric"], primary["row"]
    other_m = "logical_qubits" if metric == "physical_qubits" else "physical_qubits"
    other = requirement(rows, primary["target"], other_m)
    sub = f'{e(date_label(row.get("published", ""), short=True))} paper'
    if other:
        sub += f' · also {e(short_count(other[other_m]))} {e(_words(other_m))} qubits'
    tiles = [("Needed today", f'{e(short_count(primary["need"]))} {e(_words(metric))} qubits', sub)]
    pts = series(rows, primary["target"], metric)
    if len(pts) >= 2 and pts[0]["y"] > primary["need"]:
        tiles.append(("Since the first estimate", f'down {pct_label(1 - primary["need"] / pts[0]["y"])}',
                      f'from {e(short_count(pts[0]["y"]))} in {e(date_label(pts[0]["date"], short=True))}'))
    else:
        tiles.append(("Since the first estimate", "no change", "no earlier figure to compare"))
    if not crow["safe"]:
        sup = primary["path"].get("supply")
        if sup:
            tiles.append(("Machine announced", f'{e(short_count(sup[metric]))} by {e(year_label(int(primary["path"]["year"]), sup.get("target_month")))}',
                          f'{e(sup["actor"])}, enough for this attack'))
        else:
            tiles.append(("Machine announced", "none big enough yet", "vendor plans checked daily"))
    else:
        tiles.append(("In practice", "not practical", "needs far too many steps in a row"))
    html_ = "".join(f'<div class="stat"><span class="st-l">{l}</span><span class="st-v">{v}</span><span class="st-s">{sb}</span></div>'
                    for l, v, sb in tiles)
    return f'<div class="stats">{html_}</div>'


def _qubit_cell(value, drop, label_):
    if value is None:
        return f'<td class="num dim" data-l="{label_}">n/a</td>'
    tag = f'<small class="chg">down {pct_label(drop)}</small>' if drop else ""
    return f'<td class="num" data-l="{label_}">{e(short_count(value))}{tag}</td>'


def papers_table_html(prows):
    body = "".join(
        f'<tr><td class="dt">{e(date_label(r["published"], short=True))}</td>'
        f'<td><a href="{e(r["url"])}">{e(clean(r["title"], 140))}</a><small>{e(paper_id(r["id"]))}</small></td>'
        f'{_qubit_cell(r["physical_qubits"], r["phys_drop"], "Physical qubits")}{_qubit_cell(r["logical_qubits"], r["log_drop"], "Logical qubits")}'
        f'<td class="num" data-l="Run time">{e(duration(r["runtime"])) if r["runtime"] is not None else "n/a"}</td></tr>'
        for r in prows)
    return ('<div class="tbl"><table class="papers"><thead><tr><th>Date</th><th>Paper</th><th class="num">Physical qubits</th>'
            '<th class="num">Logical qubits</th><th class="num">Run time</th></tr></thead>'
            f'<tbody>{body}</tbody></table></div>')


def breaks_for(hw, lines):
    """Names of the attacks a vendor's announced machine is big enough for (same kind of qubit, at least as many)."""
    return [ln["name"] + (" (small 512-bit size only)" if ln["target"] in PROXY_TARGETS else "")
            for ln in lines if ln["practical"] and hw.get(ln["metric"]) is not None and hw[ln["metric"]] >= ln["need"]]


def vendor_timeline_html(actor, entries, lines=()):
    steps, known = [], set()
    for entry in sorted(entries, key=lambda x: (x.get("target_year", 0), x.get("target_month") or 13)):
        yr = int(entry["target_year"])
        yl = year_label(yr, entry.get("target_month"))
        pq, lq = short_count(entry.get("physical_qubits")), short_count(entry.get("logical_qubits"))
        parts = []
        if pq:
            parts.append(f"{pq} physical")
        if lq:
            parts.append(f"{lq} logical")
        can = [n for n in breaks_for(entry, lines) if n not in known]
        tag = (f'<span class="rm-breaks">{"Also could" if known else "Could"} break: {e(", ".join(can))}</span>' if can else "")
        known.update(can)
        steps.append(f'<div class="rm-step"><span class="rm-year">{e(yl)}</span>'
                     f'<span class="rm-qubits">{e(" / ".join(parts))} qubits</span>{tag}</div>')
    url = entries[0].get("url", "")
    link = f'<a class="rm-source" href="{e(url)}">Source</a>' if url else ""
    return f'<div class="vendor-card"><h3>{e(actor)}</h3><div class="rm-timeline">{"".join(steps)}</div>{link}</div>'


# ---------------------------------------------------------------------------
# Page bodies
# ---------------------------------------------------------------------------

PQ_LABELS = {"protected": ("pq-yes", "Protected"), "migrating": ("pq-part", "Rolling out"),
             "partial": ("pq-part", "Partly protected"), "none": ("pq-no", "No PQ protection yet"),
             "unknown": ("pq-no", "Not confirmed")}


def services_html(crows, pq_overrides=None, facts=None):
    pq_overrides = pq_overrides or {}
    facts = facts or {}
    slug_year = {}
    for crow in crows:
        yr = _label(crow) if crow["year"] else None
        slug_year[crow["slug"]] = (yr, crow["safe"], crow.get("proxy"))
    items = []
    for name, note, slug, pq, detail in SERVICES:
        fact = facts.get(name) or {}
        if fact.get("answer") or fact.get("pq_status"):  # a person's line ("pq_status") or a confirmed source ("answer")
            pq = fact.get("answer") or fact["pq_status"]
        elif pq_overrides.get(name, {}).get("pq_status"):
            pq = pq_overrides[name]["pq_status"]
        if fact.get("note"):
            detail = fact["note"]
        elif fact.get("quote"):
            detail = clean(fact["quote"], 170)
        src = (f' <a href="{e(fact["url"])}" class="svc-src">Source</a>' if fact.get("url") else "")
        yr, safe, proxy = slug_year.get(slug, (None, False, False))
        if safe:
            status_cls, status_txt = "safe", "Safe"
        elif yr:
            status_cls, status_txt = "dated", f"{yr}{'+ ' if proxy else ''}"
        else:
            status_cls, status_txt = "warn", "TBD"
        pq_cls, pq_txt = PQ_LABELS.get(pq, PQ_LABELS["unknown"])
        checked = f' <span class="dim">checked {e(date_label(fact["checked"]))}</span>' if fact.get("checked") else ""
        items.append(
            f'<div class="svc"><a class="svc-main" href="threats/{e(slug)}/">'
            f'<span class="svc-name">{e(name)}</span>'
            f'<span class="svc-note">{e(note)}</span></a>'
            f'<p class="svc-detail">{e(detail)}{src}{checked}</p>'
            f'<span class="svc-foot">'
            f'<span class="svc-pq {pq_cls}">{pq_txt}</span>'
            f'<span class="svc-yr {status_cls}">{e(status_txt)}</span>'
            f'</span></div>')
    return (f'<section class="svc-section"><h2>What you use</h2>'
            f'<div class="svc-grid">{"".join(items)}</div></section>')


def gloss_html():
    items = "".join(f"<dt>{e(t)}</dt><dd>{e(d)}</dd>" for t, d in GLOSSARY)
    return f'<details class="gloss"><summary>New to this? What the words mean</summary><dl>{items}</dl></details>'


def home_body(crows, today, alert, pq_overrides=None, facts=None):
    cd = countdown_html(crows, today) + (gloss_html() if crows else "")
    svcs = services_html(crows, pq_overrides, facts) if crows else ""
    grid = threat_grid_html(crows) if crows else ""
    empty = '<p class="empty">No verified estimates yet. The first update has not stored any.</p>' if not crows else ""
    return (f'<section class="hero"><h1>When could quantum computers break the encryption you use?</h1>'
            f'<p class="lede">Based on how big a quantum computer published attacks need, '
            f'and the machines vendors say they will build.</p></section>'
            f'{alert}{cd}{empty}{svcs}{grid}')


def threat_body(crow, rows, hw_rows, depth, facts=None, today=None):
    root = _root(depth)
    all_targets = [ln["target"] for ln in crow["lines"]]
    primary_target = all_targets[0]

    if crow["safe"]:
        badge = '<span class="d-badge safe">Safe in practice</span>'
    elif crow["year"]:
        yr = f'{_label(crow)}{"+" if crow.get("proxy") else ""}'
        badge = f'<span class="d-badge dated">{e(yr)}</span>'
    elif crow.get("waiting"):
        badge = '<span class="d-badge warn">No machine announced yet</span>'
    else:
        badge = ""

    hero = (f'<a class="back" href="{root}">All threats</a>'
            f'<div class="t-hero"><div><h1>{e(crow["title"])}</h1>'
            f'<p class="t-what">{e(crow["what"])}</p></div>{badge}</div>')

    # Context sidebar: where you meet it + if it breaks
    algos = "".join(f'<li><strong>{e(a[0])}</strong> {e(a[1])}</li>'
                    for t in all_targets for a in ALGORITHMS if a[3] == t)
    effects = ""
    if not crow["safe"]:
        eff_data = SECURES.get(primary_target) or [("", CONSEQUENCE.get(primary_target, ""))]
        eff = "".join(f'<li>{f"<strong>{e(t)}</strong> " if t else ""}{e(x)}</li>'
                      for t, x in eff_data if x)
        if eff:
            effects = f'<div><h4>If it breaks</h4><ul>{eff}</ul></div>'
    exposed = ""
    figs = [f for f in (facts or {}).values() if f.get("kind") == "figure" and f.get("group") in all_targets and f.get("answer")]
    if figs:
        lis = "".join(f'<li><strong>{e(f["answer"])}</strong> {e(f.get("label", ""))} '
                      f'<a href="{e(f["url"])}" title="{e(clean(f.get("quote", ""), 300))}">Source</a> '
                      f'{f"<span class=dim>checked {e(date_label(f["checked"]))}</span>" if f.get("quote") else ""}</li>' for f in figs)
        exposed = f'<div><h4>How much is exposed</h4><ul>{lis}</ul></div>'
    context = (f'<aside class="t-context">'
               f'<div><h4>Where you meet it</h4><ul>{algos}</ul></div>'
               f'{effects}{exposed}'
               f'<p class="d-note">{e(SECURES_NOTE)}</p></aside>')

    stats = stats_html(crow, rows)
    note = ""
    source = ""
    if not crow["safe"]:
        dated = [ln for ln in crow["lines"] if ln.get("year")]
        primary = min(dated, key=lambda l: l["due"]) if dated else crow["lines"][0]
        r = primary["row"]
        kicker = f'{e(date_label(r.get("published", "")) or "date unknown")} · {e(paper_id(r["id"]))}'
        source = (f'<details class="d-source"><summary>The paper behind the smallest figure</summary>'
                  f'<p class="d-kicker">{kicker}</p><h3>{e(clean(r["title"], 160))}</h3>'
                  f'<blockquote>{e(clean(r["quote"], 700))}</blockquote>'
                  f'<a class="read" href="{e(r["url"])}">Read the paper</a></details>')
    else:
        parts = [CONSEQUENCE.get(ln["target"], "") for ln in crow["lines"]]
        note = "".join(f'<p class="t-summary">{e(x)}</p>' for x in parts if x)

    prog = progress_cards_html(all_targets, rows, today)

    hw_section = ""
    if not crow["safe"]:
        relevant = [hw for hw in hw_rows if breaks_for(hw, crow["lines"])]
        if relevant:
            actors = {}
            for hw in relevant:
                actors.setdefault(hw["actor"], []).append(hw)
            hw_cards = "".join(vendor_timeline_html(a, ents, crow["lines"]) for a, ents in sorted(actors.items()))
            hw_section = (f'<section class="t-section"><h2>Machines big enough</h2>'
                          f'<p class="dim">Announced plans from vendors. Not delivered machines.</p>'
                          f'<div class="vendor-grid">{hw_cards}</div></section>')

    prows = paper_rows(rows, set(all_targets))
    papers = ""
    if prows:
        papers = (f'<section class="t-section"><h2>The papers ({len(prows)})</h2>'
                  f'<p class="dim">Newest first. A red change is a new low: how much smaller than the best figure before it.</p>'
                  f'{papers_table_html(prows)}{source}</section>')

    return f'{hero}{stats}{note}{prog}{context}{hw_section}{papers}'


def research_body(rows):
    sections = []
    for target, name, _who, _status in CHART_GROUPS:
        prows = paper_rows(rows, {target})
        if not prows:
            continue
        sections.append(f'<section class="r-section"><h2>{e(label(target)[0])} ({len(prows)})</h2>'
                        f'<p class="dim">{e(label(target)[1])}</p>{papers_table_html(prows)}</section>'
                        if label(target)[1] else
                        f'<section class="r-section"><h2>{e(label(target)[0])} ({len(prows)})</h2>{papers_table_html(prows)}</section>')
    return (f'<section class="hero"><h1>Every paper we track</h1>'
            f'<p class="lede">Each figure is quoted from the paper and checked against its text. Lower qubit counts mean an easier attack.</p>'
            f'</section>{"".join(sections)}')


def hardware_body(hw_rows, lines=()):
    actors = {}
    for hw in hw_rows:
        actors.setdefault(hw["actor"], []).append(hw)
    vendor_cards = "".join(vendor_timeline_html(a, ents, lines) for a, ents in sorted(actors.items()))
    return (f'<section class="hero"><h1>Machines vendors plan to build</h1>'
            f'<p class="lede">How many qubits each says it will have, and by when. Plans, not delivered machines. '
            f'"Could break" marks a machine at least as big as the smallest attack we know of.</p></section>'
            f'<div class="vendor-grid">{vendor_cards}</div>')


def chart_body(lines, narrow_lines, phys, logi, today, alt):
    if not lines:
        return '<p class="empty">No data for the chart yet.</p>'
    return (f'<section class="hero compact"><h1>Machines versus attacks</h1>'
            '<p class="lede">An attack becomes possible once a machine\'s orange line is above its black line. '
            'Height is qubits on a log scale, so each gridline is ten times the one below.</p></section>'
            '<div class="chartwrap full">'
            f'<div class="tl-wide">{chart.overview_svg(lines, phys, logi, 1060, 520, alt, today)}</div>'
            f'<div class="tl-narrow">{chart.overview_svg(narrow_lines, phys, logi, 380, 440, alt, today, narrow=True)}</div>'
            '<p class="legend"><span class="li"><span class="k line"></span>Biggest machine announced (physical qubits)</span>'
            '<span class="li"><span class="k line dashed"></span>same in logical qubits</span>'
            '<span class="li"><span class="k need"></span>Qubits an attack needs, named at the right</span>'
            '<span class="li"><span class="k ring"></span>First year a machine is big enough</span></p>'
            '</div>')


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build(out="site", data="data"):
    out, data = Path(out), Path(data)
    shutil.rmtree(out, ignore_errors=True)
    shutil.copytree(WEB / "fonts", out / "assets" / "fonts", ignore=shutil.ignore_patterns("*.ttf"))
    shutil.copy(WEB / "favicon.svg", out / "assets" / "favicon.svg")
    for sub in ("css/pages",):
        (out / "assets" / sub).mkdir(parents=True)

    assets = Assets()
    for rel in ("css/base.css", "css/pages/index.css", "css/pages/inner.css"):
        body = (WEB / rel).read_bytes()
        (out / "assets" / rel).write_bytes(body)
        assets.add(rel, body)

    def _load(name):
        src = data / name
        raw = json.loads(src.read_text()) if src.exists() else []
        if isinstance(raw, list):
            raw = [{k: (strip_dashes(v) if k in ("quote", "title") else v) for k, v in r.items()} if isinstance(r, dict) else r for r in raw]
        return raw

    (out / ".nojekyll").write_text("")

    rows = _load("attacks.json")
    hw_rows = _load("hardware.json")
    pq_overrides = json.loads((data / "pq_status.json").read_text()) if (data / "pq_status.json").exists() else {}
    facts = json.loads((data / "facts.json").read_text()) if (data / "facts.json").exists() else {}
    st = json.loads((data / "status.json").read_text()) if (data / "status.json").exists() else {}
    as_of = (st.get("run_at") or "")[:10]
    updated = datetime_label(st.get("run_at") or "") or "not yet"
    url = base_url()

    has_img = cardimg.render(rows, hw_rows, as_of, out / "assets" / "card.png", WEB / "fonts",
                             url.split("//", 1)[-1].rstrip("/"))
    home_card = cards.home_card(rows, hw_rows, as_of, url, url + "assets/card.png" if has_img else None)

    alert = ""

    lines = chart_lines(rows, hw_rows)
    narrow_lines = chart_lines(rows, hw_rows, narrow=True)
    phys = supply_points(hw_rows, "physical_qubits")
    logi = supply_points(hw_rows, "logical_qubits")
    today = year_frac(as_of) or 2026.9
    alt = "Quantum computer size each attack needs, against the machines vendors announced, by year."
    crows = countdown_rows(lines)

    # --- Home ---
    body = home_body(crows, today, alert, pq_overrides, facts)
    (out / "index.html").write_text(
        shell(body, home_card, assets, ("css/base.css", "css/pages/index.css"), 0, updated))

    # --- Threat detail pages ---
    for crow in crows:
        slug = crow["slug"]
        d = out / "threats" / slug
        d.mkdir(parents=True, exist_ok=True)
        tbody = threat_body(crow, rows, hw_rows, 2, facts, today)
        tcard = page_card(f"{crow['title']} | Quantum threat tracker",
                          f"When could quantum computers break {crow['title'].lower()}?",
                          f"{url}threats/{slug}/")
        (d / "index.html").write_text(
            shell(tbody, tcard, assets, ("css/base.css", "css/pages/inner.css"), 2, updated))

    # --- Research ---
    rd = out / "research"
    rd.mkdir(parents=True, exist_ok=True)
    queued = json.loads((data / "queue.json").read_text()) if (data / "queue.json").exists() else {}
    queued_ids = {k.rsplit("@", 1)[0] for k in queued}
    radar = [r for r in radar_rows(data / "candidates") if r.get("id") not in queued_ids]
    radar_html = ""
    if radar or queued:
        waiting = (f'<p class="dim">{len(queued)} paper{"s are" if len(queued) != 1 else " is"} waiting to be re-checked '
                   "because the preferred checking model was unavailable. It is retried automatically.</p>") if queued else ""
        listed = ('<p class="dim">Nothing is waiting on the papers below. They never change the charts and stay listed '
                  'so nothing is hidden.</p><ul>' + "".join(
                      f'<li><a href="{e(r["url"])}">{e(clean(r["title"], 100))}</a> '
                      f'<span class="dim">{e(plain_reason(r.get("reason")))}</span></li>'
                      for r in radar) + "</ul>") if radar else ""
        radar_html = (f'<details class="radar"><summary>Found but not confirmed ({len(radar)}'
                      f'{f", {len(queued)} waiting" if queued else ""})</summary>{waiting}{listed}</details>')
    rbody = research_body(rows) + radar_html
    rcard = page_card("Research | Quantum threat tracker",
                      "Published quantum attack estimates, quoted from papers.", f"{url}research/")
    (rd / "index.html").write_text(
        shell(rbody, rcard, assets, ("css/base.css", "css/pages/inner.css"), 1, updated, "research"))

    # --- Hardware ---
    hd = out / "hardware"
    hd.mkdir(parents=True, exist_ok=True)
    hbody = hardware_body(hw_rows, lines)
    hcard = page_card("Hardware | Quantum threat tracker",
                      "Quantum computer vendors' announced roadmaps.", f"{url}hardware/")
    (hd / "index.html").write_text(
        shell(hbody, hcard, assets, ("css/base.css", "css/pages/inner.css"), 1, updated, "hardware"))

    # --- Chart ---
    ch = out / "chart"
    ch.mkdir(parents=True, exist_ok=True)
    cbody = chart_body(lines, narrow_lines, phys, logi, today, alt)
    ccard = page_card("Chart | Quantum threat tracker", alt, f"{url}chart/")
    (ch / "index.html").write_text(
        shell(cbody, ccard, assets, ("css/base.css", "css/pages/inner.css"), 1, updated, "chart"))

    return out


if __name__ == "__main__":
    print(build(*sys.argv[1:]))
