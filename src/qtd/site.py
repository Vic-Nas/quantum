"""Build the static site: a countdown that answers 'when', with a detail card per threat below."""
import hashlib
import html
import json
import os
import shutil
import sys
from pathlib import Path

from . import cardimg, cards, chart
from .breakdate import METRICS, earliest_path, requirement, supply_points
from .present import (ALGORITHMS, ALGORITHMS_NOTE, CHART_GROUPS, CONSEQUENCE, COUNTDOWN, PROXY_TARGETS, SECURES, SECURES_NOTE, clean, count, date_label,
                      dom_id, duration, paper_id, plain_reason, short_count, strip_dashes, year_frac, year_label)

WEB = Path("web")
DEFAULT_URL = "https://vic-nas.github.io/quantum/"


def base_url() -> str:
    url = (os.environ.get("QTD_SITE_URL") or "").strip() or DEFAULT_URL
    return url if url.endswith("/") else url + "/"


def e(x) -> str:
    return html.escape(str(x if x is not None else ""), quote=True)


def head(card, css_hrefs):
    t = [f"<title>{e(card['title'])}</title>",
         f'<meta name="description" content="{e(card["description"])}">',
         f'<meta property="og:site_name" content="{e(card["site_name"])}">',
         f'<meta property="og:type" content="{e(card["type"])}">',
         f'<meta property="og:title" content="{e(card["title"])}">',
         f'<meta property="og:description" content="{e(card["description"])}">',
         f'<meta property="og:url" content="{e(card["url"])}">',
         f'<meta name="twitter:card" content="{"summary_large_image" if card.get("image") else "summary"}">',
         f'<meta name="theme-color" content="{e(card["theme_color"])}">',
         '<link rel="icon" href="assets/favicon.svg" type="image/svg+xml">']
    if card.get("image"):
        t += [f'<meta property="og:image" content="{e(card["image"])}">',
              f'<meta property="og:image:width" content="{card["image_width"]}">',
              f'<meta property="og:image:height" content="{card["image_height"]}">',
              f'<meta property="og:image:alt" content="{e(card["image_alt"])}">']
    t += [f'<link rel="stylesheet" href="{e(h)}">' for h in css_hrefs]
    return "\n".join(t)


def _words(metric):
    return "physical" if metric.startswith("phys") else "logical"


def chart_lines(rows, hw_rows, narrow=False):
    """One entry per attack on the chart: its cheapest published size, the kind of qubit, and the earliest announced year."""
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
    """Plain-language rows for the front page: earliest announced year per thing people care about."""
    by = {ln["target"]: ln for ln in lines}
    out = []
    for title, what, targets in COUNTDOWN:
        mine = [by[t] for t in targets if t in by]
        if not mine:
            continue
        dated = [ln for ln in mine if ln["practical"] and ln["year"]]
        proxy = any(ln["target"] in PROXY_TARGETS for ln in dated)
        out.append({"title": title, "what": what, "id": mine[0]["id"], "year": min((ln["year"] for ln in dated), default=None),
                    "safe": not any(ln["practical"] for ln in mine), "proxy": proxy,
                    "waiting": any(ln["practical"] for ln in mine) and not dated,
                    "lines": mine})
    return out


def countdown_html(crows, today):
    """The front-page countdown: one bar per row from today to the earliest announced year."""
    years = [r["year"] for r in crows if r["year"]]
    if not years:
        return ""
    x0, x1 = today, max(years) + 1.0
    pct = lambda x: 100 * (x - x0) / (x1 - x0)
    ticks = "".join(f'<span class="yr" style="left:{pct(y + 0.5):.2f}%">{y}</span>' for y in range(int(x0), int(x1)) if y + 0.5 > x0)
    grid = "".join(f'<i class="gl" style="left:{pct(y):.2f}%"></i>' for y in range(int(x0) + 1, int(x1) + 1) if x0 < y < x1)
    rows = []
    for n, r in enumerate(crows):
        cid = f"d-{dom_id(r['id'])}"
        if r["safe"]:
            track = '<span class="safe">Safe in practice</span>'
        elif r["year"]:
            end = pct(r["year"] + 1.0)
            track = f'<span class="bar" style="width:{end:.2f}%"><b>{r["year"]}{" or later" if r["proxy"] else ""}</b></span>'
        else:
            track = '<span class="safe">No announced machine is big enough yet</span>'
        rows.append(f'<a class="row{" first" if n == 0 else ""}" href="#{cid}">'
                    f'<span class="who"><strong>{e(r["title"])}</strong><small>{e(r["what"])}</small></span>'
                    f'<span class="track">{grid}{track}</span></a>')
    return (f'<section class="cd" aria-label="When it could break"><div class="axis"><span class="who"></span>'
            f'<span class="track">{ticks}</span></div>{"".join(rows)}'
            '<p class="foot">Each bar runs from today to the earliest year a vendor has announced a machine big enough. '
            'Plans, not delivered machines.</p></section>')


def detail_card(crow):
    """One detail section for a countdown row: threat, source paper, and impact."""
    cid = f"d-{dom_id(crow['id'])}"

    if crow["safe"]:
        badge_text = "Safe in practice"
        badge_cls = "safe"
    elif crow["year"]:
        badge_text = f'{crow["year"]}{" or later" if crow.get("proxy") else ""}'
        badge_cls = "warn" if crow.get("proxy") else "dated"
    elif crow.get("waiting"):
        badge_text = "No machine is big enough yet"
        badge_cls = "warn"
    else:
        badge_text = ""
        badge_cls = "warn"

    top = (f'<section class="detail" id="{cid}">'
           f'<div class="d-top"><h2>{e(crow["title"])}</h2>'
           f'<span class="d-badge {badge_cls}">{e(badge_text)}</span></div>'
           f'<p class="d-what">{e(crow["what"])}</p>')

    algos = "".join(f'<li><strong>{e(a[0])}</strong> {e(a[1])}</li>'
                    for ln in crow["lines"] for a in ALGORITHMS if a[3] == ln["target"])

    if crow["safe"]:
        parts = [CONSEQUENCE.get(ln["target"], "") for ln in crow["lines"]]
        explain = "</p><p class=\"d-explain\">".join(x for x in parts if x)
        return (f'{top}<p class="d-explain">{e(explain)}</p>'
                f'<h4>Where you meet it</h4><ul>{algos}</ul></section>')

    dated = [ln for ln in crow["lines"] if ln.get("year")]
    primary = min(dated, key=lambda l: l["year"]) if dated else crow["lines"][0]
    r = primary["row"]
    p = primary["path"]

    size = short_count(r[primary["metric"]])
    mw = _words(primary["metric"])
    threat = f'The cheapest published attack needs <strong>{e(size)} {mw} qubits</strong>.'
    if p.get("supply"):
        s = p["supply"]
        ms = short_count(s[primary["metric"]])
        yl = year_label(int(p["year"]), s.get("target_month"))
        threat += f' {e(s["actor"])} plans {e(ms)} by {e(yl)}.'

    runtime = ""
    if r.get("runtime") is not None:
        runtime = f'<p class="d-run">Runs in about {e(duration(r["runtime"]))}.</p>'

    kicker = f'{e(date_label(r.get("published", "")) or "date unknown")} &middot; {e(paper_id(r["id"]))}'
    source = (f'<div class="d-source"><p class="d-kicker">{kicker}</p>'
              f'<h3>{e(clean(r["title"], 160))}</h3>'
              f'<blockquote>{e(clean(r["quote"], 700))}</blockquote>'
              f'<a class="read" href="{e(r["url"])}">Read the paper</a></div>')

    effects = SECURES.get(primary["target"]) or [("", CONSEQUENCE.get(primary["target"], ""))]
    eff = "".join(f'<li>{f"<strong>{e(t)}</strong> " if t else ""}{e(x)}</li>' for t, x in effects if x)

    impact = (f'<div class="d-grid"><div><h4>Where you meet it</h4><ul>{algos}</ul></div>'
              f'<div><h4>If it breaks</h4><ul>{eff}</ul></div></div>')
    note = f'<p class="d-note">{e(SECURES_NOTE)}</p>'

    return f'{top}<p class="d-threat">{threat}</p>{runtime}{source}{impact}{note}</section>'


def tech_chart_html(lines, narrow_lines, phys, logi, today, alt):
    """Collapsed technical overview: the full chart with all attacks and announced machines."""
    if not lines:
        return ""
    return ('<details class="tech"><summary>Technical overview: all attacks and announced machines</summary>'
            '<div class="chartwrap">'
            f'<div class="tl-wide">{chart.overview_svg(lines, phys, logi, 1060, 440, alt, today)}</div>'
            f'<div class="tl-narrow">{chart.overview_svg(narrow_lines, phys, logi, 380, 440, alt, today, narrow=True)}</div>'
            '<p class="legend"><span class="li"><span class="k line"></span>Machines vendors announced: physical qubits</span>'
            '<span class="li"><span class="k line dashed"></span>logical qubits</span>'
            '<span class="li"><span class="k need"></span>Size an attack needs (solid: physical, dashed: logical)</span>'
            '<span class="li"><span class="k ring"></span>Where a machine passes it</span></p>'
            '</div></details>')


def radar_rows(path):
    """Papers whose latest outcome is Tier B (found, not confirmed)."""
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


def build(out="site", data="data"):
    out, data = Path(out), Path(data)
    shutil.rmtree(out, ignore_errors=True)
    (out / "data").mkdir(parents=True)
    shutil.copytree(WEB / "fonts", out / "assets" / "fonts", ignore=shutil.ignore_patterns("*.ttf"))
    shutil.copy(WEB / "favicon.svg", out / "assets" / "favicon.svg")
    for sub in ("css/pages", "js"):
        (out / "assets" / sub).mkdir(parents=True)
    hrefs, scripts = [], []
    for rel in ("css/base.css", "css/pages/index.css", "js/index.js"):
        body = (WEB / rel).read_bytes()
        (out / "assets" / rel).write_bytes(body)
        (hrefs if rel.endswith(".css") else scripts).append(f"assets/{rel}?v={hashlib.sha256(body).hexdigest()[:10]}")
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
    has_img = cardimg.render(rows, hw_rows, as_of, out / "assets" / "card.png", WEB / "fonts", base_url().split("//", 1)[-1].rstrip("/"))
    card = cards.home_card(rows, hw_rows, as_of, base_url(), base_url() + "assets/card.png" if has_img else None)
    gate_ok = (st.get("gate") or {}).get("ok", True)
    problems = list((st.get("source_errors") or {}).items())
    alert = ""
    if problems or not gate_ok:
        why = "; ".join(f"{k}: {clean(v, 80)}" for k, v in problems) or "the safety check failed, so new papers are held back"
        alert = f'<p class="alert" role="alert"><strong>The last update had a problem.</strong> {e(why)}</p>'
    lines = chart_lines(rows, hw_rows)
    narrow_lines = chart_lines(rows, hw_rows, narrow=True)
    phys, logi = supply_points(hw_rows, "physical_qubits"), supply_points(hw_rows, "logical_qubits")
    today = year_frac(as_of) or 2026.9
    alt = "Quantum computer size each attack needs, against the machines vendors announced, by year."

    crows = countdown_rows(lines)
    cd = countdown_html(crows, today)
    details = "".join(detail_card(crow) for crow in crows)
    tech = tech_chart_html(lines, narrow_lines, phys, logi, today, alt)

    body = (cd + f'<div class="details">{details}</div>' + tech) if lines else '<p class="empty">No verified estimates yet. The first update has not stored any.</p>'

    queued = json.loads((data / "queue.json").read_text()) if (data / "queue.json").exists() else {}
    queued_ids = {k.rsplit("@", 1)[0] for k in queued}
    radar = [r for r in radar_rows(data / "candidates") if r.get("id") not in queued_ids]
    radar_html = ""
    if radar or queued:
        waiting = (f'<p class="dim">{len(queued)} paper{"s are" if len(queued) != 1 else " is"} waiting to be re-checked '
                   "because the preferred checking model was unavailable. It is retried automatically.</p>") if queued else ""
        listed = ("<p class=\"dim\">Nothing is waiting on the papers below. They never change the charts and stay listed so nothing is hidden.</p><ul>" + "".join(
                          f'<li><a href="{e(r["url"])}">{e(clean(r["title"], 100))}</a> <span class="dim">{e(plain_reason(r.get("reason")))}</span></li>'
                          for r in radar) + "</ul>") if radar else ""
        radar_html = (f'<details class="radar"><summary>Found but not confirmed ({len(radar)}'
                      f'{f", {len(queued)} waiting" if queued else ""})</summary>{waiting}{listed}</details>')
    updated = date_label(as_of) or "not yet"
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
{head(card, hrefs)}
</head><body>
<header class="bar"><span class="brand"><img src="assets/favicon.svg" alt="" width="22" height="22">Quantum threat tracker</span><span class="upd">Updated {e(updated)}</span></header>
<main class="page">
<section class="hero"><h1>When could quantum computers break the encryption you use?</h1>
<p class="lede">Based on how big a quantum computer published attacks need, and the machines vendors say they will build.</p></section>
{alert}{body}

{radar_html}
<footer><span>Every figure is quoted from a paper or vendor page and checked against its text. The lists of what is affected are written by hand.</span><a href="data/attacks.json">Raw data</a></footer>
</main>{"".join(f'<script src="{e(s)}" defer></script>' for s in scripts)}</body></html>"""
    (out / "index.html").write_text(page)
    return out


if __name__ == "__main__":
    print(build(*sys.argv[1:]))
