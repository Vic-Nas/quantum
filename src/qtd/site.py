"""Build the static site: one front page with a timeline per target, proof on click."""
import hashlib
import html
import json
import os
import shutil
import sys
from pathlib import Path

from . import cardimg, cards, chart
from .breakdate import METRICS, earliest_path, requirement, supply_points
from .present import (ALGORITHMS, ALGORITHMS_NOTE, SECURES, SECURES_NOTE, TARGET_NAMES, TARGET_ORDER, clean, count, date_label, dom_id, duration, headline,
                      label, paper_id, plain_reason, series, short_count, strip_dashes, year_frac)

WEB = Path("web")
DEFAULT_URL = "https://vic-nas.github.io/quantum/"


def base_url() -> str:
    """Public address from QTD_SITE_URL (a repo variable). Empty or unset falls back to the default."""
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


def proof(r, selected):
    """The evidence card for one source: what it says, in its own words."""
    hw = r.get("kind") == "hardware"
    bits = []
    if r.get("physical_qubits") is not None:
        bits.append(f'<span class="big">{e(short_count(r["physical_qubits"]))}</span> physical qubits')
    if r.get("logical_qubits") is not None:
        bits.append(f'<span class="big">{e(count(r["logical_qubits"]))}</span> error-corrected (logical) qubits')
    if hw:
        kicker = f'{e(r.get("actor"))} roadmap &middot; target year {e(int(r["target_year"]))}'
        head_, label_, read = clean(r["title"], 160), "What the vendor's page says", "Read the vendor's page"
        run = '<span class="run">A plan or target, not a delivered machine.</span>'
    else:
        kicker = f'{e(date_label(r.get("published", "")) or "date unknown")} &middot; {e(paper_id(r["id"]))}'
        head_, label_, read = clean(r["title"], 160), "What the paper says", "Read the paper"
        run = f'<span class="run">Runs in about {e(duration(r["runtime"]))}.</span>' if r.get("runtime") is not None else ""
    return (f'<article class="proof{" is-sel" if selected else ""}" id="{dom_id(r["id"])}">'
            f'<p class="kicker">{kicker}</p><h3>{e(head_)}</h3>'
            f'<p class="fig">{" and ".join(bits)}</p>{run}'
            f'<p class="qlabel">{label_}</p><blockquote>{e(clean(r["quote"], 700))}</blockquote>'
            f'<a class="read" href="{e(r["url"])}">{read}</a></article>')


def _words(metric):
    return "physical qubits" if metric.startswith("phys") else "error-corrected (logical) qubits"


def target_section(rows, hw_rows, target, today=None):
    name, _ = label(target)
    mine = [r for r in rows if r.get("target") == target]
    if not mine:
        return ""
    path = earliest_path(rows, hw_rows, target)
    metric = path.get("metric")
    if not metric:  # no crossing: still chart a metric that has both a requirement and announced machines
        metric = next((m for m in METRICS if requirement(rows, target, m) and supply_points(hw_rows, m)), None)
    pts = series(rows, target)
    alt = f"When could {name} be broken? Announced machine sizes by year against the size needed."
    if metric:
        need_row = requirement(rows, target, metric)
        sup = supply_points(hw_rows, metric)
        by = path.get("year")
        main = (f'<div class="chart"><div class="tl-wide">{chart.break_svg(sup, need_row, metric, by, 640, 330, alt, today or 2026.9)}</div>'
                f'<div class="tl-narrow">{chart.break_svg(sup, need_row, metric, by, 340, 300, alt, today or 2026.9)}</div>'
                '<p class="legend"><span class="li"><span class="k rec"></span>Largest announced so far</span>'
                '<span class="li"><span class="k"></span>Other announced machines</span>'
                '<span class="li"><span class="k need"></span>Size the cheapest known attack needs</span>'
                '<span class="li"><span class="k zone"></span>An announced machine is big enough</span></p>'
                '<p class="dim pad">Plans, not delivered machines. Physical qubits are real hardware; logical qubits are error-corrected groups of them.</p></div>')
        default_id = (path["supply"]["id"] if by else need_row["id"])
        sub = (f'Earliest announced path: <strong>{by}</strong>. The cheapest known attack needs '
               f'{e(short_count(path["need"]))}; {e(path["supply"]["actor"])} announced '
               f'{e(short_count(path["supply"][path["metric"]]))} by {by}.') if by else (
               f'No date: {e(path["reason"])}.')
    else:
        main = ('<div class="chart"><p class="dim pad">No vendor announcement in the same kind of qubit has been collected yet, so a break date cannot be '
                'drawn. The dots below show how small the published attacks have become.</p></div>')
        default_id = mine[0]["id"]
        sub = f'No date: {e(path["reason"])}.'
    hist = ""
    if pts:
        h_alt = f"Qubits needed to break {name}, by paper date."
        hist = ('<details class="history"><summary>How the size needed fell, paper by paper</summary>'
                f'<div class="chart"><div class="tl-wide">{chart.timeline_svg(pts, 640, 330, h_alt, today)}</div>'
                f'<div class="tl-narrow">{chart.timeline_svg(pts, 340, 300, h_alt, today)}</div>'
                '<p class="legend"><span class="li"><span class="k rec"></span>Set a new record</span>'
                '<span class="li"><span class="k"></span>Other estimates</span>'
                '<span class="li"><span class="k line"></span>Best known so far</span></p>'
                '<p class="dim pad">Here the dates are when each paper was published, not when anything could be broken.</p></div></details>')
    ordered = sorted(mine, key=lambda r: r.get("published", ""), reverse=True)
    hw_used = [h for h in hw_rows if h.get(metric or "physical_qubits") is not None] if metric else []
    proofs = "".join(proof(r, r["id"] == default_id) for r in ordered + sorted(hw_used, key=lambda h: h.get("target_year", 0)))
    also = [r for r in ordered if r.get("physical_qubits") is None]
    also_html = ""
    if also and any(r.get("logical_qubits") is not None for r in also):
        also_html = ('<p class="also"><span>Also published (counts error-corrected qubits only):</span> ' + " ".join(
            f'<a href="#{dom_id(r["id"])}" data-id="{dom_id(r["id"])}">{e(count(r["logical_qubits"]))} logical, {e(date_label(r.get("published", ""), True))}</a>'
            for r in also if r.get("logical_qubits") is not None) + "</p>")
    secures = "".join(f"<li><strong>{e(a)}</strong><span>{e(b)}</span></li>" for a, b in SECURES.get(target, []))
    secures_html = (f'<div class="protects"><h3>What this protects, and what happens if it breaks</h3><ul>{secures}</ul>'
                    f'<p class="dim">{e(SECURES_NOTE)}</p></div>') if secures else ""
    pname, tech = TARGET_NAMES.get(target, (name, name))
    return (f'<section class="target" id="t-{e(target)}" role="tabpanel" aria-labelledby="tab-{e(target)}">'
            f'<header><h2>{e(pname)}</h2><p>{sub}</p></header>'
            f'<div class="viz">{main}<aside class="proofs" aria-live="polite">{proofs}</aside></div>{hist}{also_html}{secures_html}</section>')


def tiles(rows, hw_rows, targets):
    out = []
    for n, t in enumerate(targets):
        pname, tech = TARGET_NAMES.get(t, label(t))
        path = earliest_path(rows, hw_rows, t)
        h = headline(rows, t)
        if path.get("year"):
            nums = f'<span class="now">{path["year"]}</span>'
            cap = "earliest announced path to break it"
            more = (f'Needs {e(short_count(path["need"]))} {_words(path["metric"])}; {e(path["supply"]["actor"])} '
                    f'plans {e(short_count(path["supply"][path["metric"]]))} by {path["year"]}')
        else:
            nums = '<span class="now none">No date yet</span>'
            cap, more = e(path["reason"]), ""
        fell = (f'Size needed fell {h["drop_pct"]:g}%, {e(date_label(h["first"]["date"], True))} to {e(date_label(h["best"]["date"], True))}'
                if h and h["first"] is not h["best"] else "")
        out.append(f'<a class="hl{" is-active" if n == 0 else ""}" id="tab-{e(t)}" role="tab" href="#t-{e(t)}" data-tab="t-{e(t)}" '
                   f'aria-selected="{"true" if n == 0 else "false"}"><span class="what">{e(pname)}</span><span class="tech">{e(tech)}</span>'
                   f'<span class="nums">{nums}</span><span class="cap">{cap}</span>'
                   f'{f"<span class=cap>{more}</span>" if more else ""}{f"<span class=cap>{fell}</span>" if fell else ""}</a>')
    return "".join(out)


def algorithms_tile(n_active):
    broken = sum(1 for a in ALGORITHMS if a[2] == "broken")
    weak = sum(1 for a in ALGORITHMS if a[2] == "weakened")
    charted = len({a[0] for a in ALGORITHMS if a[3]})
    return (f'<a class="hl" id="tab-all" role="tab" href="#t-all" data-tab="t-all" aria-selected="false"><span class="what">Everything affected</span>'
            f'<span class="tech">Every algorithm in common use</span><span class="nums"><span class="now">{broken}</span></span>'
            f'<span class="cap">families broken, {weak} more weakened</span><span class="cap">{charted} of the {broken} broken are charted here</span></a>')


def algorithms_section():
    rows = "".join(
        f'<tr><td><strong>{e(name)}</strong></td><td>{e(used)}</td><td class="st {e(st)}">{e(st.capitalize())}</td>'
        f'<td>{f"<a href=#t-{e(tid)} data-tab=t-{e(tid)}>{e(note)}</a>" if tid else e(note)}</td></tr>'
        for name, used, st, tid, note in ALGORITHMS)
    return ('<section class="target" id="t-all" role="tabpanel" aria-labelledby="tab-all"><header><h2>Everything a quantum computer affects</h2>'
            f'<p>{e(ALGORITHMS_NOTE)}</p></header><div class="algos"><table><thead><tr><th>Algorithm</th><th>Where you meet it</th>'
            f'<th>Quantum threat</th><th>On this page</th></tr></thead><tbody>{rows}</tbody></table></div></section>')


def radar_rows(path):
    """Papers whose latest outcome is Tier B (found, not confirmed). One line per paper; never affects the charts."""
    latest = {}
    if not path.exists():
        return []
    for f in sorted(path.glob("*.jsonl")):
        for line in f.read_text().splitlines():
            r = json.loads(line)
            latest[r.get("id") or r.get("url", "")] = r
    def chartable(r):
        ests = r.get("estimates") or []
        return not ests or any(e["values"].get("physical_qubits") is not None or e["values"].get("logical_qubits") is not None for e in ests)
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
        if isinstance(raw, list):  # the served copy has dashes removed from quoted text; the stored data stays verbatim
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
    present = sorted({r.get("target") for r in rows}, key=lambda t: (TARGET_ORDER.index(t) if t in TARGET_ORDER else 99, str(t)))
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
    body = "".join(target_section(rows, hw_rows, t, year_frac(as_of)) for t in present) if rows else (
        '<p class="empty">No verified estimates yet. The first update has not stored any.</p>')
    updated = date_label(as_of) or "not yet"
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<script>document.documentElement.className+=" js"</script>
{head(card, hrefs)}
</head><body>
<header class="bar"><span class="brand"><img src="assets/favicon.svg" alt="" width="22" height="22">Quantum threat tracker</span><span class="upd">Updated {e(updated)}</span></header>
<main class="page">
<section class="hero"><h1>How close is quantum computing to breaking today's encryption?</h1>
<p class="lede">The machine size the cheapest published attack needs, against the machines vendors plan to build. The year they meet is the
earliest announced path to a break. Plans, not delivered machines.</p>
<div class="hls" role="tablist" aria-label="What to look at">{tiles(rows, hw_rows, present)}{algorithms_tile(0)}</div></section>
{alert}{body}{algorithms_section()}

{radar_html}
<footer><span>Every figure is quoted from a paper or vendor page and checked against its text. The lists of what is affected are written by hand.</span><a href="data/attacks.json">Raw data</a></footer>
</main>{"".join(f'<script src="{e(s)}" defer></script>' for s in scripts)}</body></html>"""
    (out / "index.html").write_text(page)
    return out


if __name__ == "__main__":
    print(build(*sys.argv[1:]))
