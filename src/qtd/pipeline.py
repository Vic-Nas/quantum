"""Daily run: fetch, dedupe, prefilter, regex baseline, model stages, verify, route, auto-apply.

Policy: automation may only make the security picture look worse. A Tier A row is a cheaper
attack or a new hardware claim, so it is applied automatically, behind automatic brakes
(canary check, per-run cap) and every change is one reversible commit.
"""
import datetime as dt
import json
from pathlib import Path

from . import llm, regex_extract, router, sources, stages
from .prefilter import prefilter
from .verify import any_agrees, verify

DATA = Path("data")
MAX_ATTEMPTS = 12     # give up on an item after this many failed model runs (retries run every 2 hours)
MAX_AUTO_PER_RUN = 3  # more new headline rows than this in one run is held for a person
ROWS = {"attack": "attacks.json", "hardware": "hardware.json"}


def _verified(extraction, item):
    return verify(extraction, stages.source_text(item), sources.is_allowlisted(item["url"]))


def dedupe_estimates(ests: list) -> list:
    """Drop an estimate whose values are all contained in a richer estimate of the same paper.

    A result can be quoted from both the title and the abstract; the richer one (more fields) wins.
    """
    keep = []
    for i, a in enumerate(ests):
        av = a["values"]
        dominated = any(
            j != i and bv.get("target") == av.get("target") and all(bv.get(k) == v for k, v in av.items())
            and (len(bv) > len(av) or (len(bv) == len(av) and j < i))
            for j, b in enumerate(ests) for bv in [b["values"]])
        if not dominated:
            keep.append(a)
    return keep


def process(item: dict, rows: list, use_llm: bool) -> dict:
    """Run one item through every stage. Raises llm.LLMError if the models are unavailable."""
    rec = {"id": item["id"], "version": item["version"], "url": item["url"], "title": item["title"],
           "published": item["published"], "tier": "drop", "reason": "", "estimates": [], "trail": {}}
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
    c, m = llm.call_chain("coarse", lambda mod: stages.coarse(item, mod))
    rec["trail"]["coarse"] = {**c, "model": m}
    if not c.get("relevant"):
        rec["reason"] = "coarse filter"
        return rec
    ex1, m1 = llm.call_chain("primary", lambda mod: stages.extract(item, mod))
    v1 = _verified(ex1, item)
    rec["trail"]["primary"] = {"model": m1, "extraction": ex1, "estimates": v1["estimates"]}
    v2, m2 = None, None
    needs = [e for e in v1["ok_estimates"]
             if v1["kind"] == "hardware" or router.is_frontier(e["values"], rows)]
    if needs:
        ex2, m2 = llm.call_chain("secondary", lambda mod: stages.extract(item, mod), exclude=m1)
        v2 = _verified(ex2, item)
        rec["trail"]["secondary"] = {"model": m2, "extraction": ex2, "estimates": v2["estimates"]}
    independent = bool(m2) and m2 != m1  # a different model; the family is logged so this can be tightened later
    unconfirmed = [e for e in needs if not (v2 and any_agrees(e["values"], v2["ok_estimates"]))]
    if m2 and m2 != llm.CHAINS["secondary"][0] and unconfirmed:
        # The second opinion came from a fallback model. Do not demote a good row for good because the
        # preferred model was down; the queue retries it on a later run.
        raise llm.LLMError(f"second opinion came from fallback model {m2}, retrying later")
    for e in v1["estimates"]:
        second = independent and e["ok"] and any_agrees(e["values"], v2["ok_estimates"] if v2 else [])
        tier, why = router.route(v1["kind"], e["ok"], e["values"], second, rows)
        if v2 and not independent and tier == "A":
            tier, why = "B", "second opinion came from the same model as the first"
        rec["estimates"].append({"kind": v1["kind"], "values": e["values"], "quote": e["quote"], "tier": tier,
                                 "reason": why, "regex_agrees": e["ok"] and any_agrees(e["values"], rx_v["ok_estimates"])})
    rec["estimates"] = dedupe_estimates(rec["estimates"])
    order = {"A": 0, "B": 1, "drop": 2}
    best = min(rec["estimates"], key=lambda x: order[x["tier"]], default=None)
    rec["tier"], rec["reason"] = (best["tier"], best["reason"]) if best else ("drop", "no estimates")
    rec["models"] = {"primary": m1, "secondary": m2,
                     "different_family": bool(m2) and llm.family(m1) != llm.family(m2)}
    return rec


def canary(n: int = 2) -> dict:
    """Re-check known papers WITHOUT the cache. If the models fail, auto-apply is switched off."""
    gold = [json.loads(l) for l in (DATA / "gold" / "gold.jsonl").read_text().splitlines() if l.strip()]
    picks = [g for g in gold if g.get("canary")][:n]
    if not picks:
        return {"ok": True, "skipped": "no canary items"}
    try:
        for g in picks:
            ex, _ = llm.call_chain("primary", lambda mod: llm.generate(
                mod, stages.extract_prompt(g), stages.EXTRACT_SCHEMA, use_cache=False))
            ests = [{"quote": e.get("quote", ""), "fields": {f["name"]: f["value"] for f in e.get("fields", [])}}
                    for e in ex.get("estimates", [])]
            v = verify({"kind": ex.get("kind"), "estimates": ests}, stages.source_text(g))
            for want in g["estimates"]:
                from .evaluate import _match
                if not any(_match(e["values"], want) for e in v["ok_estimates"]):
                    return {"ok": False, "failed": g["id"], "missing": want}
    except llm.LLMError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True}


def _row(rec: dict, est: dict, n: int) -> dict:
    vals = {k: (round(v, 6) if isinstance(v, float) else v) for k, v in est["values"].items()}
    return {"id": f"{rec['id']}#{n}", "kind": est["kind"], **vals, "quote": est["quote"],
            "url": rec["url"], "title": rec["title"], "published": rec["published"],
            "added": dt.date.today().isoformat(), "models": rec.get("models"),
            "verification": "auto: verifier + two model families agree", "regex_agrees": est["regex_agrees"]}


def _load(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def run(use_llm: bool = True, limit: int | None = None, items: list | None = None,
        auto_apply: bool = True, dry: bool = False, max_auto: int = MAX_AUTO_PER_RUN,
        check_canary: bool = True):
    """Run the pipeline. dry=True writes nothing. Returns a summary dict."""
    errors = {}
    if items is None:
        items, errors = sources.fetch_all()
    seen = set(_load(DATA / "seen.json", []))
    queue = _load(DATA / "queue.json", {})
    rows = {k: _load(DATA / f, []) for k, f in ROWS.items()}
    work = [(i, queue.get(f"{i['id']}@{i['version']}", {}).get("attempts", 0)) for i in items
            if f"{i['id']}@{i['version']}" not in seen]
    queued_keys = {f"{i['id']}@{i['version']}" for i in items}
    work += [(q["item"], q["attempts"]) for k, q in queue.items() if k not in queued_keys]
    work = work[:limit]
    month = dt.date.today().strftime("%Y-%m")
    counts = {"A": 0, "B": 0, "drop": 0, "retry": 0, "gave_up": 0}
    recs, applied, held = [], [], []
    for it, attempts in work:
        key = f"{it['id']}@{it['version']}"
        try:
            rec = process(it, rows["attack"], use_llm)
        except llm.LLMError as e:
            attempts += 1
            if attempts >= MAX_ATTEMPTS:
                counts["gave_up"] += 1
                seen.add(key)
                queue.pop(key, None)
                recs.append({"id": it["id"], "version": it["version"], "url": it["url"], "title": it["title"],
                             "tier": "B", "reason": f"models unavailable after {attempts} tries: {e}",
                             "estimates": [], "trail": {}})
            else:
                counts["retry"] += 1
                queue[key] = {"item": it, "attempts": attempts, "last_error": str(e)[:200]}
            continue
        counts[rec["tier"]] += 1
        queue.pop(key, None)
        seen.add(key)
        recs.append(rec)
    gate = canary() if (check_canary and use_llm and auto_apply and any(r["tier"] == "A" for r in recs)) else {"ok": True}
    new_a = [(r, e) for r in recs for e in r["estimates"] if e["tier"] == "A"]
    allow = auto_apply and gate["ok"] and len(new_a) <= max_auto
    for n, (r, e) in enumerate(new_a):
        (applied if allow else held).append((r, e, n))
    if not dry:
        (DATA / "candidates").mkdir(parents=True, exist_ok=True)
        (DATA / "proposals").mkdir(parents=True, exist_ok=True)
        if use_llm:
            with open(DATA / "candidates" / f"{month}.jsonl", "a") as out:
                for r in recs:
                    out.write(json.dumps(r) + "\n")
            for r, e, n in applied:
                rows[e["kind"]].append(_row(r, e, n))
            for kind, f in ROWS.items():
                (DATA / f).write_text(json.dumps(rows[kind], indent=1))
            for r, e, n in held:
                name = r["id"].replace(":", "_").replace("/", "_") + f"_{n}"
                (DATA / "proposals" / f"{name}.json").write_text(json.dumps({"rec": r, "est": e, "gate": gate}, indent=1))
            (DATA / "seen.json").write_text(json.dumps(sorted(seen)))
            (DATA / "queue.json").write_text(json.dumps(queue, indent=1))
    summary = {"fetched": len(items), "processed": len(work), "counts": counts, "source_errors": errors,
               "auto_applied": len(applied), "held": len(held), "gate": gate,
               "queue_size": len(queue), "dry": dry or not use_llm}
    if not dry and use_llm:
        (DATA / "status.json").write_text(json.dumps(
            {**summary, "run_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}, indent=1))
    return summary


def seed():
    """Rebuild the baseline from data/seed_papers.json through the normal verified path.

    Fetches each paper from arXiv (so dates are real), clears the old seed rows and applies every
    Tier A row. Later daily runs then compare against this baseline instead of an empty table.
    """
    ids = _load(DATA / "seed_papers.json", {}).get("ids", [])
    items = sources.fetch_arxiv_ids(ids)
    for it in items:
        it["version"] = "seed"
    keys = {f"{i['id']}@seed" for i in items}
    seen = set(_load(DATA / "seen.json", [])) - keys
    (DATA / "seen.json").write_text(json.dumps(sorted(seen)))
    for f in ROWS.values():
        (DATA / f).write_text("[]")
    return run(items=items, max_auto=10**6, check_canary=False)


def retry():
    """Re-check only the queued papers. Does nothing (no fetch, no model call) when the queue is empty."""
    if not _load(DATA / "queue.json", {}):
        return {"processed": 0, "queue_size": 0, "idle": True}
    return run(items=[])
