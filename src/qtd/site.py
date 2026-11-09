"""Build the static site: one front page with a timeline per target, proof on click."""
import hashlib
import html
import json
import os
import shutil
import sys
from pathlib import Path

from . import cardimg, cards, chart
from .present import (SECURES, SECURES_NOTE, TARGET_NAMES, TARGET_ORDER, clean, count, date_label, dom_id, duration, headline,
                      label, paper_id, plain_reason, series, short_count)

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
    """The evidence card for one paper: what it says, in its own words."""
    bits = []
    if r.get("physical_qubits") is not None:
        bits.append(f'<span class="big">{e(short_count(r["physical_qubits"]))}</span> physical qubits')
    if r.get("logical_qubits") is not None:
        bits.append(f'<span class="big">{e(count(r["logical_qubits"]))}</span> error-corrected (logical) qubits')
    run = f'<span class="run">Runs in about {e(duration(r["runtime"]))}.</span>' if r.get("runtime") is not None else ""
    when = date_label(r.get("published", "")) or "date unknown"
    return (f'<article class="proof{" is-sel" if selected else ""}" id="{dom_id(r["id"])}">'
            f'<p class="kicker">{e(when)} &middot; {e(paper_id(r["id"]))}</p>'
            f'<h3>{e(clean(r["title"], 160))}</h3>'
            f'<p class="fig">{" and ".join(bits)}</p>{run}'
            f'<p class="qlabel">What the paper says</p><blockquote>{e(clean(r["quote"], 700))}</blockquote>'
            f'<a class="read" href="{e(r["url"])}">Read the paper</a></article>')


def target_section(rows, target):
    pts = series(rows, target)
    name, _ = label(target)
    mine = [r for r in rows if r.get("target") == target]
    if not mine:
        return ""
    best = min(pts, key=lambda p: (p["y"], -p["x"]))["row"]["id"] if pts else mine[0]["id"]
    ordered = sorted(mine, key=lambda r: r.get("published", ""), reverse=True)
    proofs = "".join(proof(r, r["id"] == best) for r in ordered)
    alt = f"Qubits needed to break {name}, by paper date. Lower is closer to breaking it."
    charts = ""
    if pts:
        charts = (f'<div class="chart"><div class="tl-wide">{chart.timeline_svg(pts, 640, 330, alt)}</div>'
                  f'<div class="tl-narrow">{chart.timeline_svg(pts, 340, 300, alt)}</div>'
                  '<p class="legend"><span class="li"><span class="k rec"></span>Set a new record</span>'
                  '<span class="li"><span class="k"></span>Other estimates</span>'
                  '<span class="li"><span class="k line"></span>Best known so far</span></p></div>')
    else:
        charts = '<div class="chart"><p class="dim">No estimate here states physical qubits, so there is nothing to chart yet.</p></div>'
    also = [r for r in ordered if r.get("physical_qubits") is None]
    also_html = ""
    if also:
        also_html = ('<p class="also"><span>Also published, not on the chart (counts error-corrected qubits only):</span> ' + " ".join(
            f'<a href="#{dom_id(r["id"])}" data-id="{dom_id(r["id"])}">{e(count(r["logical_qubits"]))} logical, {e(date_label(r.get("published", ""), True))}</a>'
            for r in also if r.get("logical_qubits") is not None) + "</p>")
    secures = "".join(f"<li><strong>{e(a)}</strong><span>{e(b)}</span></li>" for a, b in SECURES.get(target, []))
    secures_html = (f'<div class="protects"><h3>What this protects, and what happens if it breaks</h3><ul>{secures}</ul>'
                    f'<p class="dim">{e(SECURES_NOTE)}</p></div>') if secures else ""
    pname, tech = TARGET_NAMES.get(target, (name, name))
    return (f'<section class="target" id="t-{e(target)}" role="tabpanel" aria-labelledby="tab-{e(target)}">'
            f'<header><h2>{e(pname)}</h2><p>Secured by {e(tech)}. Each dot is a published estimate of the quantum computer size needed to break it.</p></header>'
            f'<div class="viz">{charts}<aside class="proofs" aria-live="polite">{proofs}</aside></div>{also_html}{secures_html}</section>')


def tiles(rows, targets):
    out = []
    for n, t in enumerate(targets):
        h = headline(rows, t)
        pname, tech = TARGET_NAMES.get(t, label(t))
        if not h:
            continue
        now = short_count(h["best"]["y"])
        if h["first"] is not h["best"]:
            nums = (f'<span class="was">{e(short_count(h["first"]["y"]))}</span><span class="arrow" aria-label="down to">&rarr;</span>'
                    f'<span class="now">{e(now)}</span>')
            cap = (f'qubits needed, {e(date_label(h["first"]["date"], True))} to {e(date_label(h["best"]["date"], True))}'
                   f' ({h["drop_pct"]:g}% smaller)')
        else:
            nums, cap = f'<span class="now">{e(now)}</span>', f'qubits needed, {e(date_label(h["best"]["date"], True))}'
        out.append(f'<a class="hl{" is-active" if n == 0 else ""}" id="tab-{e(t)}" role="tab" href="#t-{e(t)}" data-tab="t-{e(t)}" '
                   f'aria-selected="{"true" if n == 0 else "false"}"><span class="what">{e(pname)}</span><span class="tech">{e(tech)}</span>'
                   f'<span class="nums">{nums}</span><span class="cap">{cap}</span></a>')
    return "".join(out)


def radar_rows(path):
    """Papers whose latest outcome is Tier B (found, not confirmed). One line per paper; never affects the charts."""
    latest = {}
    if not path.exists():
        return []
    for f in sorted(path.glob("*.jsonl")):
        for line in f.read_text().splitlines():
            r = json.loads(line)
            latest[r.get("id") or r.get("url", "")] = r
    return [r for r in latest.values() if r.get("tier") == "B"][:25]


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
        (out / "data" / f).write_text(src.read_text() if src.exists() else "[]")
    (out / ".nojekyll").write_text("")
    rows = json.loads((out / "data" / "attacks.json").read_text())
    st = json.loads((data / "status.json").read_text()) if (data / "status.json").exists() else {}
    as_of = (st.get("run_at") or "")[:10]
    has_img = cardimg.render(rows, as_of, out / "assets" / "card.png", WEB / "fonts", base_url().split("//", 1)[-1].rstrip("/"))
    card = cards.home_card(rows, as_of, base_url(), base_url() + "assets/card.png" if has_img else None)
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
    body = "".join(target_section(rows, t) for t in present) if rows else (
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
<p class="lede">Today's security holds because nobody can build a big enough quantum computer. Researchers keep publishing smaller
designs. Pick what you care about, then click any dot to read the paper's own words.</p>
<div class="hls" role="tablist" aria-label="What to look at">{tiles(rows, present)}</div></section>
{alert}{body}
<section class="notes"><h2>How to read this</h2>
<dl><div><dt>Qubit</dt><dd>The basic unit of a quantum computer, like a bit in an ordinary one. Breaking encryption takes many of them working together.</dd></div>
<div><dt>Physical vs. error-corrected</dt><dd>A physical qubit is one real piece of hardware. Error-corrected (logical) qubits are built from many physical ones, so they are not comparable with the charted numbers.</dd></div>
<div><dt>Not a countdown</dt><dd>This shows how big a machine would have to be. It does not yet track how big machines are today, so it cannot say when. Each paper assumes its own kind of hardware, so look at the trend and not at exact comparisons.</dd></div></dl></section>
{radar_html}
<footer><span>Figures are sentences quoted from each paper and checked against its text. The descriptions of what each algorithm protects are written by hand.</span><a href="data/attacks.json">Raw data</a></footer>
</main>{"".join(f'<script src="{e(s)}" defer></script>' for s in scripts)}</body></html>"""
    (out / "index.html").write_text(page)
    return out


if __name__ == "__main__":
    print(build(*sys.argv[1:]))
