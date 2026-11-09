"""Build the static site: index.html, hashed CSS, self-hosted fonts and the raw JSON feed."""
import hashlib
import html
import json
import os
import shutil
import sys
from pathlib import Path

from . import cards
from .present import best_by_target, clean, count, duration, label, paper_id

WEB = Path("web")
DEFAULT_URL = "https://vic-nas.github.io/quantum/"


def base_url() -> str:
    """Public address from QTD_SITE_URL (a repo variable). Empty or unset falls back to the default."""
    url = (os.environ.get("QTD_SITE_URL") or "").strip() or DEFAULT_URL
    return url if url.endswith("/") else url + "/"
EXT = '<svg class="ext" aria-hidden="true"><use href="#i-ext"/></svg>'
SPRITE = ('<svg width="0" height="0" style="position:absolute" aria-hidden="true"><symbol id="i-ext" viewBox="0 0 12 12">'
          '<path d="M4 2h6v6M10 2 3 9" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>'
          "</symbol></svg>")


def e(x) -> str:
    return html.escape(str(x if x is not None else ""), quote=True)


def head(card, css_hrefs):
    t = [f"<title>{e(card['title'])} | {e(card['site_name'])}</title>",
         f'<meta name="description" content="{e(card["description"])}">',
         f'<meta property="og:site_name" content="{e(card["site_name"])}">',
         f'<meta property="og:type" content="{e(card["type"])}">',
         f'<meta property="og:title" content="{e(card["title"])}">',
         f'<meta property="og:description" content="{e(card["description"])}">',
         f'<meta property="og:url" content="{e(card["url"])}">',
         '<meta name="twitter:card" content="summary">',
         f'<meta name="theme-color" content="{e(card["theme_color"])}">']
    if card.get("image"):
        t.append(f'<meta property="og:image" content="{e(card["image"])}">')
    t += [f'<link rel="stylesheet" href="{e(h)}">' for h in css_hrefs]
    return "\n".join(t)


def fmt_time(iso):
    return iso.replace("T", " ")[:16] + " UTC" if iso else "never"


def summary_rows(rows):
    out = []
    for target, b in best_by_target(rows).items():
        name, sub = label(target)
        p, lq = b["physical"], b["logical"]
        def src(r):
            return f'<a class="mono" href="{e(r["url"])}" title="{e(clean(r["title"], 160))}">{e(paper_id(r["id"]))}{EXT}</a>' if r else ""
        out.append(
            f'<tr><td data-label="Target"><span class="tname">{e(name)}</span><span class="small">{e(sub)}</span></td>'
            f'<td class="num" data-label="Fewest physical qubits">{f'<span class="big">{count(p["physical_qubits"])}</span>' if p else '<span class="big none">not published</span>'}'
            f'<span class="small">{e(duration(p.get("runtime"))) if p and p.get("runtime") is not None else ""}</span></td>'
            f'<td class="num" data-label="Fewest logical qubits">{f'<span class="big">{count(lq["logical_qubits"])}</span>' if lq else '<span class="big none">not published</span>'}</td>'
            f'<td data-label="Source">{src(p or lq)}</td>'
            f'<td class="num" data-label="Estimates">{b["n"]}</td></tr>')
    return "".join(out)


def detail_rows(rows):
    key = lambda r: (str(r.get("target")), r.get("physical_qubits") if r.get("physical_qubits") is not None else 1e99)
    out = []
    for r in sorted(rows, key=key):
        out.append(
            f'<tr><td class="nowrap">{e(label(r.get("target"))[0])}</td>'
            f'<td class="num">{count(r.get("physical_qubits"))}</td><td class="num">{count(r.get("logical_qubits"))}</td>'
            f'<td class="num">{e(duration(r.get("runtime")))}</td><td class="num">{count(r.get("toffoli_or_t_count"))}</td>'
            f'<td><a href="{e(r["url"])}">{e(clean(r["title"], 70))}{EXT}</a>'
            f'<details><summary></summary><blockquote>{e(clean(r["quote"], 700))}</blockquote></details></td>'
            f'<td class="num dim">{e(r.get("added", ""))}</td></tr>')
    return "".join(out)


def radar_rows(path):
    """Tier B items from the audit trail: found but not confirmed. Never affects the numbers."""
    out = []
    if not path.exists():
        return out
    for f in sorted(path.glob("*.jsonl"), reverse=True):
        for line in reversed(f.read_text().splitlines()):
            r = json.loads(line)
            if r.get("tier") == "B":
                out.append(r)
    return out[:25]


def build(out="site", data="data"):
    out, data = Path(out), Path(data)
    shutil.rmtree(out, ignore_errors=True)
    (out / "data").mkdir(parents=True)
    shutil.copytree(WEB / "fonts", out / "assets" / "fonts")
    (out / "assets" / "css" / "pages").mkdir(parents=True)
    hrefs = []
    for rel in ("css/base.css", "css/pages/index.css"):
        body = (WEB / rel).read_bytes()
        (out / "assets" / rel).write_bytes(body)
        hrefs.append(f"assets/{rel}?v={hashlib.sha256(body).hexdigest()[:10]}")
    for f in ("attacks.json", "hardware.json", "status.json", "queue.json"):
        src = data / f
        (out / "data" / f).write_text(src.read_text() if src.exists() else "[]")
    (out / ".nojekyll").write_text("")
    rows = json.loads((out / "data" / "attacks.json").read_text())
    st_path = data / "status.json"
    st = json.loads(st_path.read_text()) if st_path.exists() else {}
    as_of = (st.get("run_at") or "")[:10]
    card = cards.home_card(rows, as_of, base_url())
    gate_ok = (st.get("gate") or {}).get("ok", True)
    problems = list((st.get("source_errors") or {}).items())
    health = ("bad", "Needs attention") if (problems or not gate_ok) else (("ok", "Pipeline healthy") if st else ("warn", "No run yet"))
    radar = radar_rows(data / "candidates")
    alert = ""
    if problems or not gate_ok:
        why = "; ".join(f"{k}: {clean(v, 80)}" for k, v in problems) or "the canary check failed, so new rows are held"
        alert = f'<p class="alert" role="alert"><strong>Last run needs attention.</strong> {e(why)}</p>'
    table_summary = (f'<div class="scroll"><table class="summary"><thead><tr><th>Target</th>'
                     f'<th class="num">Fewest physical qubits</th><th class="num">Fewest logical qubits</th><th>Source</th>'
                     f'<th class="num">Estimates</th></tr></thead><tbody>{summary_rows(rows)}</tbody></table></div>'
                     if rows else '<div class="empty"><strong>No estimates yet</strong><p>The first run has not stored any verified estimate.</p></div>')
    table_all = (f'<div class="scroll"><table class="wide"><thead><tr><th>Target</th><th class="num">Physical qubits</th>'
                 f'<th class="num">Logical qubits</th><th class="num">Runtime</th><th class="num">Toffoli gates</th>'
                 f'<th>Paper and verbatim quote</th><th class="num">Added</th></tr></thead><tbody>{detail_rows(rows)}</tbody></table></div>'
                 if rows else "")
    radar_html = ("".join(
        f'<tr><td><a href="{e(r["url"])}">{e(clean(r["title"], 90))}{EXT}</a></td><td class="dim">{e(clean(r.get("reason"), 120))}</td></tr>'
        for r in radar))
    radar_panel = (f'<div class="scroll"><table><thead><tr><th>Paper</th><th>Why it is not in the numbers</th></tr></thead>'
                   f"<tbody>{radar_html}</tbody></table></div>" if radar else
                   '<div class="empty"><strong>Nothing waiting</strong><p>Papers the pipeline found but could not confirm appear '
                   "here. They never change the figures above.</p></div>")
    c = st.get("counts") or {}
    kv = [("Papers checked", st.get("processed", "")),
          ("New rows applied", st.get("auto_applied", "")), ("Held for review", st.get("held", "")),
          ("Waiting for models", st.get("queue_size", "")), ("Gave up after retries", c.get("gave_up", "")),
          ("Canary check", "passed" if gate_ok else "failed")]
    kv_html = "".join(f"<div><dt>{e(k)}</dt><dd>{e(v)}</dd></div>" for k, v in kv)
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
{head(card, hrefs)}
</head><body class="p-home">{SPRITE}
<header class="bar"><a class="brand" href="./">Quantum threat tracker</a>
<nav aria-label="Main"><a href="./" aria-current="page">Estimates</a><a href="data/attacks.json">Data</a>
<a href="https://github.com/Vic-Nas/quantum">Source</a></nav><span class="spacer"></span>
<span class="pill"><span class="dot {health[0]}"></span>{e(health[1])}</span></header>
<main class="page">
<div class="page-head"><div><h1>Cheapest known quantum attacks</h1>
<p class="lede">Published resource estimates only. Every figure comes from a quote that was checked against the paper's text,
and nothing here is earlier than what has been publicly announced.</p></div>
<span class="pill">Updated {e(fmt_time(st.get("run_at")))}</span></div>
{alert}
<div class="cols c-3-2">
<section class="panel" aria-labelledby="h-low"><header><h2 id="h-low">Lowest published figures, by target</h2>
<span class="sub">{len(rows)} verified estimates</span></header>
{table_summary}
<p class="note">Qubit counts depend on each paper's assumptions (qubit type, error rate, error-correcting code).
Figures from different architectures are not directly comparable, so read the quote before comparing them.</p></section>
<div>
<section class="panel mb" aria-labelledby="h-date"><header><h2 id="h-date">Earliest break date</h2>
<span class="sub">not computed</span></header>
<div class="empty"><strong>Needs two more datasets</strong><p>A date needs announced hardware (qubits, error rates, roadmaps) and the list of systems
each key protects. Neither has been collected yet, so no date is shown.</p></div></section>
<section class="panel" aria-labelledby="h-run"><header><h2 id="h-run">Last run</h2></header>
<dl class="kv">{kv_html}</dl></section></div></div>
<section class="panel mb" aria-labelledby="h-all"><header><h2 id="h-all">All estimates</h2>
<span class="sub">sorted by target, then physical qubits</span></header>{table_all}</section>
<section class="panel" aria-labelledby="h-radar"><header><h2 id="h-radar">Radar (unreviewed)</h2>
<span class="sub">{len(radar)} items</span></header>{radar_panel}</section>
<footer><span>Data: <a href="data/attacks.json">attacks.json</a>, <a href="data/status.json">status.json</a></span>
<span>Models propose and code verifies. Two model families must agree before a row is applied.</span></footer>
</main></body></html>"""
    (out / "index.html").write_text(page)
    return out


if __name__ == "__main__":
    print(build(*sys.argv[1:]))
