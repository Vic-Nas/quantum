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
from .breakdate import METRICS, earliest_path, requirement, supply_points
from .present import (ALGORITHMS, ALGORITHMS_NOTE, CHART_GROUPS, CONSEQUENCE, COUNTDOWN,
                      PROXY_TARGETS, SECURES, SECURES_NOTE, clean, count, date_label,
                      dom_id, duration, headline, label, paper_id, plain_reason, series,
                      short_count, strip_dashes, year_frac, year_label)

WEB = Path("web")
DEFAULT_URL = "https://vic-nas.github.io/quantum/"
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
<header class="bar">
<a class="brand" href="{root}"><img src="{root}assets/favicon.svg" alt="" width="22" height="22">Quantum threat tracker</a>
{nav_html(nav_active, depth)}
<span class="upd">Updated {e(updated)}</span>
</header>
<main class="page">{body}</main>
<footer><span>Every figure is quoted from a paper or vendor page and checked against its text. The lists of what is affected are written by hand.</span><a href="{root}data/attacks.json">Raw data</a></footer>
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
        if not practical:
            when = "not practical"
        elif year:
            when = f"{year} or later" if target in PROXY_TARGETS else str(year)
        else:
            when = "none announced"
        size = short_count(need_row[metric])
        out.append({"id": dom_id(need_row["id"]), "name": name, "need": need_row[metric], "metric": metric, "year": year,
                    "practical": practical, "when": when, "who": who, "target": target, "row": need_row, "path": path,
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
        out.append({"title": title, "what": what, "id": mine[0]["id"],
                    "year": min((ln["year"] for ln in dated), default=None),
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

def countdown_html(crows, today):
    years = [r["year"] for r in crows if r["year"]]
    if not years:
        return ""
    x0, x1 = today, max(years) + 1.0
    pct = lambda x: 100 * (x - x0) / (x1 - x0)
    ticks = "".join(f'<span class="yr" style="left:{pct(y + 0.5):.2f}%">{y}</span>'
                    for y in range(int(x0), int(x1)) if y + 0.5 > x0)
    grid = "".join(f'<i class="gl" style="left:{pct(y):.2f}%"></i>'
                   for y in range(int(x0) + 1, int(x1) + 1) if x0 < y < x1)
    rows_html = []
    for n, r in enumerate(crows):
        href = f"threats/{r['slug']}/"
        if r["safe"]:
            track = '<span class="safe">Safe in practice</span>'
        elif r["year"]:
            end = pct(r["year"] + 1.0)
            track = f'<span class="bar" style="width:{end:.2f}%"><b>{r["year"]}{" or later" if r["proxy"] else ""}</b></span>'
        else:
            track = '<span class="safe">No announced machine is big enough yet</span>'
        rows_html.append(
            f'<a class="row{" first" if n == 0 else ""}" href="{href}">'
            f'<span class="who"><strong>{e(r["title"])}</strong><small>{e(r["what"])}</small></span>'
            f'<span class="track">{grid}{track}</span></a>')
    return (f'<section class="cd" aria-label="When it could break"><div class="axis"><span class="who"></span>'
            f'<span class="track">{ticks}</span></div>{"".join(rows_html)}'
            '<p class="foot">Each bar runs from today to the earliest year a vendor has announced a machine big enough. '
            'Plans, not delivered machines.</p></section>')


def threat_grid_html(crows):
    items = []
    for crow in crows:
        if crow["safe"]:
            badge = '<span class="tc-badge safe">Safe in practice</span>'
        elif crow["year"]:
            yr = f'{crow["year"]}{"+" if crow.get("proxy") else ""}'
            badge = f'<span class="tc-badge dated">{e(yr)}</span>'
        else:
            badge = '<span class="tc-badge warn">TBD</span>'
        items.append(
            f'<a class="threat-card" href="threats/{crow["slug"]}/">'
            f'{badge}<h3>{e(crow["title"])}</h3>'
            f'<p>{e(crow["what"])}</p>'
            f'<span class="tc-more">View details →</span></a>')
    return f'<div class="card-grid">{"".join(items)}</div>'


def progress_svg(target, rows, w=560, h=180):
    pts = series(rows, target)
    if len(pts) < 2:
        return ""
    xs = [p["x"] for p in pts]
    ys = [math.log10(max(p["y"], 1)) for p in pts]
    x0, x1 = min(xs) - 0.5, max(xs) + 0.5
    y0, y1 = min(ys) - 0.3, max(ys) + 0.3
    if y1 - y0 < 0.5:
        y0 -= 0.3
        y1 += 0.3
    pl, pr, pt, pb = 65, 20, 15, 30
    pw, ph = w - pl - pr, h - pt - pb

    def sx(v):
        return pl + (v - x0) / (x1 - x0) * pw

    def sy(v):
        return pt + (1 - (v - y0) / (y1 - y0)) * ph

    svg = [f'<svg viewBox="0 0 {w} {h}" class="prog" xmlns="http://www.w3.org/2000/svg">']
    for exp in range(int(math.floor(min(ys))), int(math.ceil(max(ys))) + 1):
        yy = sy(exp)
        svg.append(f'<line x1="{pl}" y1="{yy:.1f}" x2="{w - pr}" y2="{yy:.1f}" '
                   f'stroke="rgb(var(--ink-rgb)/.07)" stroke-width="1"/>')
        svg.append(f'<text x="{pl - 8}" y="{yy:.1f}" fill="var(--ink-dim)" font-size="11" '
                   f'font-family="var(--sans)" text-anchor="end" dominant-baseline="middle">'
                   f'{short_count(10 ** exp)}</text>')
    year_set = sorted(set(int(x) for x in xs))
    for yr in year_set:
        xx = sx(yr + 0.5)
        svg.append(f'<text x="{xx:.1f}" y="{h - 6}" fill="var(--ink-dim)" font-size="11" '
                   f'font-family="var(--sans)" text-anchor="middle">{yr}</text>')
    recs = [p for p in pts if p["record"]]
    if len(recs) >= 2:
        d = []
        for i, p in enumerate(recs):
            px, py = sx(p["x"]), sy(math.log10(max(p["y"], 1)))
            if i == 0:
                d.append(f"M{px:.1f},{py:.1f}")
            else:
                d.append(f"H{px:.1f}V{py:.1f}")
        d.append(f"H{sx(max(xs) + 0.3):.1f}")
        svg.append(f'<path d="{"".join(d)}" fill="none" stroke="var(--accent)" '
                   f'stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>')
    for p in pts:
        px, py = sx(p["x"]), sy(math.log10(max(p["y"], 1)))
        fill = "var(--accent)" if p["record"] else "var(--surface)"
        r = 4.5 if p["record"] else 3.5
        svg.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{r}" fill="{fill}" '
                   f'stroke="var(--accent)" stroke-width="1.8"/>')
    svg.append("</svg>")
    return "\n".join(svg)


def paper_card_html(r, show_target=False):
    date = date_label(r.get("published", ""), short=True)
    pid = paper_id(r["id"])
    pq, lq, rt = r.get("physical_qubits"), r.get("logical_qubits"), r.get("runtime")
    metrics = []
    if pq is not None:
        metrics.append(f"{short_count(pq)} physical qubits")
    if lq is not None:
        metrics.append(f"{short_count(lq)} logical qubits")
    if rt is not None:
        metrics.append(duration(rt))
    target_tag = ""
    if show_target:
        lbl = label(r.get("target", ""))[0]
        target_tag = f'<span class="pc-target">{e(lbl)}</span>'
    return (f'<div class="paper-card">'
            f'<div class="pc-head"><span class="pc-date">{e(date)}</span>'
            f'<span class="pc-id">{e(pid)}</span>{target_tag}</div>'
            f'<h3><a href="{e(r["url"])}">{e(clean(r["title"], 120))}</a></h3>'
            f'<p class="pc-metrics">{e(" · ".join(metrics))}</p></div>')


def vendor_timeline_html(actor, entries):
    steps = []
    for entry in sorted(entries, key=lambda x: x.get("target_year", 0)):
        yr = int(entry["target_year"])
        yl = year_label(yr, entry.get("target_month"))
        pq, lq = short_count(entry.get("physical_qubits")), short_count(entry.get("logical_qubits"))
        parts = []
        if pq:
            parts.append(f"{pq} physical")
        if lq:
            parts.append(f"{lq} logical")
        steps.append(f'<div class="rm-step"><span class="rm-year">{e(yl)}</span>'
                     f'<span class="rm-qubits">{e(" / ".join(parts))} qubits</span></div>')
    url = entries[0].get("url", "")
    link = f'<a class="rm-source" href="{e(url)}">Source</a>' if url else ""
    return f'<div class="vendor-card"><h3>{e(actor)}</h3><div class="rm-timeline">{"".join(steps)}</div>{link}</div>'


# ---------------------------------------------------------------------------
# Page bodies
# ---------------------------------------------------------------------------

def home_body(crows, today, alert):
    cd = countdown_html(crows, today)
    grid = threat_grid_html(crows) if crows else ""
    empty = '<p class="empty">No verified estimates yet. The first update has not stored any.</p>' if not crows else ""
    return (f'<section class="hero"><h1>When could quantum computers break the encryption you use?</h1>'
            f'<p class="lede">Based on how big a quantum computer published attacks need, '
            f'and the machines vendors say they will build.</p></section>'
            f'{alert}{cd}{empty}{grid}')


def threat_body(crow, rows, hw_rows, depth):
    root = _root(depth)
    all_targets = [ln["target"] for ln in crow["lines"]]
    primary_target = all_targets[0]

    if crow["safe"]:
        badge = '<span class="d-badge safe">Safe in practice</span>'
    elif crow["year"]:
        yr = f'{crow["year"]}{"+" if crow.get("proxy") else ""}'
        badge = f'<span class="d-badge dated">{e(yr)}</span>'
    elif crow.get("waiting"):
        badge = '<span class="d-badge warn">No machine announced yet</span>'
    else:
        badge = ""

    hero = (f'<a class="back" href="{root}">← All threats</a>'
            f'<div class="t-hero"><div><h1>{e(crow["title"])}</h1>'
            f'<p class="t-what">{e(crow["what"])}</p></div>{badge}</div>')

    summary = ""
    if not crow["safe"]:
        dated = [ln for ln in crow["lines"] if ln.get("year")]
        primary = min(dated, key=lambda l: l["year"]) if dated else crow["lines"][0]
        r = primary["row"]
        p = primary["path"]
        size = short_count(r[primary["metric"]])
        mw = _words(primary["metric"])
        text = f'The cheapest published attack needs <strong>{e(size)} {mw} qubits</strong>.'
        if p.get("supply"):
            s = p["supply"]
            ms = short_count(s[primary["metric"]])
            yl = year_label(int(p["year"]), s.get("target_month"))
            text += f' {e(s["actor"])} plans {e(ms)} by {e(yl)}.'
        if r.get("runtime") is not None:
            text += f' Runs in about {e(duration(r["runtime"]))}.'
        summary += f'<p class="t-summary">{text}</p>'
        kicker = f'{e(date_label(r.get("published", "")) or "date unknown")} · {e(paper_id(r["id"]))}'
        summary += (f'<div class="d-source"><p class="d-kicker">{kicker}</p>'
                    f'<h3>{e(clean(r["title"], 160))}</h3>'
                    f'<blockquote>{e(clean(r["quote"], 700))}</blockquote>'
                    f'<a class="read" href="{e(r["url"])}">Read the paper</a></div>')
    else:
        parts = [CONSEQUENCE.get(ln["target"], "") for ln in crow["lines"]]
        summary = "".join(f'<p class="t-summary">{e(x)}</p>' for x in parts if x)

    prog = ""
    for t in all_targets:
        svg = progress_svg(t, rows)
        if svg:
            tl = label(t)[0]
            prog = (f'<section class="t-section"><h2>How estimates have improved</h2>'
                    f'<p class="dim">Physical qubits needed to break {e(tl)}, log scale. '
                    f'Filled dots set a new record low.</p>{svg}</section>')
            break

    target_papers = sorted([r for r in rows if r.get("target") in all_targets],
                           key=lambda r: r.get("published", ""), reverse=True)
    papers = ""
    if target_papers:
        pcards = "".join(paper_card_html(r) for r in target_papers)
        n = len(target_papers)
        papers = (f'<section class="t-section"><h2>Published estimates ({n})</h2>'
                  f'<div class="card-grid compact">{pcards}</div></section>')

    algos = "".join(f'<li><strong>{e(a[0])}</strong> {e(a[1])}</li>'
                    for t in all_targets for a in ALGORITHMS if a[3] == t)
    effects = ""
    if not crow["safe"]:
        eff_data = SECURES.get(primary_target) or [("", CONSEQUENCE.get(primary_target, ""))]
        eff = "".join(f'<li>{f"<strong>{e(t)}</strong> " if t else ""}{e(x)}</li>'
                      for t, x in eff_data if x)
        if eff:
            effects = f'<div><h4>If it breaks</h4><ul>{eff}</ul></div>'
    impact = (f'<section class="t-section"><div class="d-grid">'
              f'<div><h4>Where you meet it</h4><ul>{algos}</ul></div>'
              f'{effects}</div></section>')
    note = f'<p class="d-note">{e(SECURES_NOTE)}</p>'

    hw_section = ""
    if not crow["safe"]:
        relevant = []
        for ln in crow["lines"]:
            need = ln["row"].get(ln["metric"])
            if need is None:
                continue
            for hw in hw_rows:
                hw_val = hw.get(ln["metric"])
                if hw_val is not None and hw_val >= need and hw not in relevant:
                    relevant.append(hw)
        if relevant:
            actors = {}
            for hw in relevant:
                actors.setdefault(hw["actor"], []).append(hw)
            hw_cards = "".join(vendor_timeline_html(a, ents) for a, ents in sorted(actors.items()))
            hw_section = (f'<section class="t-section"><h2>Hardware that could deliver</h2>'
                          f'<p class="dim">Vendor announcements with enough qubits for this attack.</p>'
                          f'<div class="vendor-grid">{hw_cards}</div></section>')

    return f'{hero}{summary}{prog}{papers}{impact}{note}{hw_section}'


def research_body(rows):
    by_target = {}
    for r in rows:
        by_target.setdefault(r.get("target", "other"), []).append(r)
    sections = []
    for target, name, _who, _status in CHART_GROUPS:
        papers = by_target.get(target, [])
        if not papers:
            continue
        papers = sorted(papers, key=lambda r: r.get("published", ""), reverse=True)
        lbl = label(target)[0]
        pcards = "".join(paper_card_html(r) for r in papers)
        sections.append(f'<section class="r-section"><h2>{e(lbl)} ({len(papers)})</h2>'
                        f'<div class="card-grid compact">{pcards}</div></section>')
    return (f'<section class="hero"><h1>Published attack estimates</h1>'
            f'<p class="lede">Every figure is quoted from a paper and checked against its text. '
            f'Sorted by target, newest first.</p></section>{"".join(sections)}')


def hardware_body(hw_rows):
    actors = {}
    for hw in hw_rows:
        actors.setdefault(hw["actor"], []).append(hw)
    vendor_cards = "".join(vendor_timeline_html(a, ents) for a, ents in sorted(actors.items()))
    return (f'<section class="hero"><h1>Hardware roadmaps</h1>'
            f'<p class="lede">Quantum computer vendors\' announced plans. '
            f'Plans, not delivered machines.</p></section>'
            f'<div class="vendor-grid">{vendor_cards}</div>')


def chart_body(lines, narrow_lines, phys, logi, today, alt):
    if not lines:
        return '<p class="empty">No data for the chart yet.</p>'
    return (f'<section class="hero"><h1>Technical overview</h1>'
            f'<p class="lede">{e(alt)}</p></section>'
            '<div class="chartwrap">'
            f'<div class="tl-wide">{chart.overview_svg(lines, phys, logi, 1060, 440, alt, today)}</div>'
            f'<div class="tl-narrow">{chart.overview_svg(narrow_lines, phys, logi, 380, 440, alt, today, narrow=True)}</div>'
            '<p class="legend"><span class="li"><span class="k line"></span>Machines vendors announced: physical qubits</span>'
            '<span class="li"><span class="k line dashed"></span>logical qubits</span>'
            '<span class="li"><span class="k need"></span>Size an attack needs (solid: physical, dashed: logical)</span>'
            '<span class="li"><span class="k ring"></span>Where a machine passes it</span></p>'
            '</div>')


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build(out="site", data="data"):
    out, data = Path(out), Path(data)
    shutil.rmtree(out, ignore_errors=True)
    (out / "data").mkdir(parents=True)
    shutil.copytree(WEB / "fonts", out / "assets" / "fonts", ignore=shutil.ignore_patterns("*.ttf"))
    shutil.copy(WEB / "favicon.svg", out / "assets" / "favicon.svg")
    for sub in ("css/pages",):
        (out / "assets" / sub).mkdir(parents=True)

    assets = Assets()
    for rel in ("css/base.css", "css/pages/index.css", "css/pages/inner.css"):
        body = (WEB / rel).read_bytes()
        (out / "assets" / rel).write_bytes(body)
        assets.add(rel, body)

    for f in ("attacks.json", "hardware.json", "status.json", "queue.json"):
        src = data / f
        raw = json.loads(src.read_text()) if src.exists() else []
        if isinstance(raw, list):
            raw = [{k: (strip_dashes(v) if k in ("quote", "title") else v) for k, v in r.items()} if isinstance(r, dict) else r for r in raw]
        (out / "data" / f).write_text(json.dumps(raw, indent=1))
    (out / ".nojekyll").write_text("")

    rows = json.loads((out / "data" / "attacks.json").read_text())
    hw_rows = json.loads((out / "data" / "hardware.json").read_text() or "[]")
    st = json.loads((data / "status.json").read_text()) if (data / "status.json").exists() else {}
    as_of = (st.get("run_at") or "")[:10]
    updated = date_label(as_of) or "not yet"
    url = base_url()

    has_img = cardimg.render(rows, hw_rows, as_of, out / "assets" / "card.png", WEB / "fonts",
                             url.split("//", 1)[-1].rstrip("/"))
    home_card = cards.home_card(rows, hw_rows, as_of, url, url + "assets/card.png" if has_img else None)

    gate_ok = (st.get("gate") or {}).get("ok", True)
    problems = list((st.get("source_errors") or {}).items())
    alert = ""
    if problems or not gate_ok:
        why = "; ".join(f"{k}: {clean(v, 80)}" for k, v in problems) or \
              "the safety check failed, so new papers are held back"
        alert = f'<p class="alert" role="alert"><strong>The last update had a problem.</strong> {e(why)}</p>'

    lines = chart_lines(rows, hw_rows)
    narrow_lines = chart_lines(rows, hw_rows, narrow=True)
    phys = supply_points(hw_rows, "physical_qubits")
    logi = supply_points(hw_rows, "logical_qubits")
    today = year_frac(as_of) or 2026.9
    alt = "Quantum computer size each attack needs, against the machines vendors announced, by year."
    crows = countdown_rows(lines)

    # --- Home ---
    body = home_body(crows, today, alert)
    (out / "index.html").write_text(
        shell(body, home_card, assets, ("css/base.css", "css/pages/index.css"), 0, updated))

    # --- Threat detail pages ---
    for crow in crows:
        slug = crow["slug"]
        d = out / "threats" / slug
        d.mkdir(parents=True, exist_ok=True)
        tbody = threat_body(crow, rows, hw_rows, 2)
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
    hbody = hardware_body(hw_rows)
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
