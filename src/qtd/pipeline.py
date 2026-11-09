"""Daily run: fetch, dedupe, prefilter, regex baseline, optional model stages, verify, route."""
import datetime as dt
import json
from pathlib import Path

from . import llm, regex_extract, router, sources, stages
from .prefilter import prefilter
from .verify import any_agrees, verify

DATA = Path("data")


def _verified(extraction, item):
    return verify(extraction, f"{item['title']} {item['text']}", sources.is_allowlisted(item["url"]))


def process(item: dict, rows: list, use_llm: bool) -> dict:
    """Run one item through every stage. Returns its audit trail with a tier per estimate."""
    rec = {"id": item["id"], "version": item["version"], "url": item["url"], "title": item["title"],
           "published": item["published"], "models": dict(llm.MODELS), "tier": "drop", "reason": "", "estimates": [], "trail": {}}
    pf = prefilter(item)
    rec["trail"]["prefilter"] = pf
    rx = regex_extract.extract(f"{item['title']}. {item['text']}")
    rx_v = _verified(rx, item)
    rec["trail"]["regex"] = {"extraction": rx, "ok_estimates": [e["values"] for e in rx_v["ok_estimates"]]}
    if not pf["keep"]:
        rec["reason"] = "prefilter"
        return rec
    if not use_llm:
        rec["tier"], rec["reason"] = "B", "no model run (regex only)"
        return rec
    try:
        c = stages.coarse(item, llm.MODELS["coarse"])
        rec["trail"]["coarse"] = c
        if not c.get("relevant"):
            rec["reason"] = "coarse filter"
            return rec
        ex1 = stages.extract(item, llm.MODELS["primary"])
        v1 = _verified(ex1, item)
        rec["trail"]["primary"] = {"extraction": ex1, "estimates": v1["estimates"]}
        ex2, v2 = None, None
        needs_second = [e for e in v1["ok_estimates"]
                        if v1["kind"] == "hardware" or router.is_frontier(e["values"], rows)]
        if needs_second:
            ex2 = stages.extract(item, llm.MODELS["secondary"])
            v2 = _verified(ex2, item)
            rec["trail"]["secondary"] = {"extraction": ex2, "estimates": v2["estimates"]}
        for e in v1["estimates"]:
            second = bool(v2) and e["ok"] and any_agrees(e["values"], v2["ok_estimates"])
            tier, why = router.route(v1["kind"], e["ok"], e["values"], second, rows)
            rec["estimates"].append({"values": e["values"], "quote": e["quote"], "tier": tier, "reason": why,
                                     "regex_agrees": e["ok"] and any_agrees(e["values"], rx_v["ok_estimates"])})
        order = {"A": 0, "B": 1, "drop": 2}
        best = min(rec["estimates"], key=lambda x: order[x["tier"]], default=None)
        rec["tier"], rec["reason"] = (best["tier"], best["reason"]) if best else ("drop", "no estimates")
    except llm.LLMError as e:
        rec["tier"], rec["reason"] = "B", f"model error: {e}"
    return rec


def _comment(rec: dict) -> str:
    """Templated PR comment built only from verified facts and quotes (no free-form model prose)."""
    lines = [f"### {rec['title']}", rec["url"], "", "| tier | values | regex agrees | verbatim quote |",
             "|---|---|---|---|"]
    for e in rec["estimates"]:
        lines.append(f"| {e['tier']} ({e['reason']}) | {e['values']} | {e['regex_agrees']} | {e['quote']} |")
    return "\n".join(lines) + "\n"


def run(use_llm: bool = True, limit: int | None = None, items: list | None = None):
    """Run the pipeline. Returns a summary dict. Writes audit trail, radar and Tier A proposals."""
    errors = {}
    if items is None:
        items, errors = sources.fetch_all()
    seen_path = DATA / "seen.json"
    seen = set(json.loads(seen_path.read_text())) if seen_path.exists() else set()
    rows = router.load_rows()
    fresh = [i for i in items if f"{i['id']}@{i['version']}" not in seen][:limit]
    month = dt.date.today().strftime("%Y-%m")
    (DATA / "candidates").mkdir(parents=True, exist_ok=True)
    (DATA / "proposals").mkdir(parents=True, exist_ok=True)
    counts = {"A": 0, "B": 0, "drop": 0}
    with open(DATA / "candidates" / f"{month}.jsonl", "a") as out:
        for it in fresh:
            rec = process(it, rows, use_llm)
            counts[rec["tier"]] += 1
            out.write(json.dumps(rec) + "\n")
            if rec["tier"] == "A":
                name = rec["id"].replace(":", "_").replace("/", "_")
                (DATA / "proposals" / f"{name}.json").write_text(json.dumps(rec, indent=1))
                (DATA / "proposals" / f"{name}.md").write_text(_comment(rec))
            seen.add(f"{it['id']}@{it['version']}")
    seen_path.write_text(json.dumps(sorted(seen)))
    return {"fetched": len(items), "new": len(fresh), "counts": counts, "source_errors": errors}
