"""Daily run: fetch, dedupe, prefilter, regex baseline, model stages, verify, route, auto-apply.

Policy: automation may only make the security picture look worse. A Tier A row is a cheaper
attack or a new hardware claim, so it is applied automatically, behind automatic brakes
(canary check, per-run cap) and every change is one reversible commit.
"""
import datetime as dt
import json
import re
from pathlib import Path

from . import llm, regex_extract, router, sources, stages
from .prefilter import prefilter
from .textutil import qubit_regime
from .verify import any_agrees, verify

DATA = Path("data")
MAX_ATTEMPTS = 12     # give up on an item after this many failed model runs (retries run every 2 hours)
MAX_AUTO_PER_RUN = 3  # more new headline rows than this in one run is held for a person
ROWS = {"attack": "attacks.json", "hardware": "hardware.json"}


def _verified(extraction, item, regime=None):
    return verify(extraction, stages.source_text(item), sources.is_allowlisted(item["url"]), regime=regime, context=item["title"])


def dedupe_estimates(ests: list) -> list:
    """Drop an estimate whose values are all contained in a richer estimate of the same paper.

    A result can be quoted from both the title and the abstract; the richer one (more fields) wins.
    """
    keep = []
    for i, a in enumerate(ests):
        av = a["values"]
        dominated = any(
            j != i and b.get("tier") != "drop" and bv.get("target") == av.get("target") and all(bv.get(k) == v for k, v in av.items())
            and (len(bv) > len(av) or (len(bv) == len(av) and j < i))
            for j, b in enumerate(ests) for bv in [b["values"]])
        if not dominated:
            keep.append(a)
    return keep


def process(item: dict, rows: list, use_llm: bool, fulltext: bool = False) -> dict:
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
    views, regime = [item], qubit_regime(f"{item['title']}. {item['text']}")
    if fulltext and item["source"] == "arxiv":
        text = sources.fetch_fulltext(item["id"])
        rec["trail"]["fulltext_chars"] = len(text)
        regime = qubit_regime(text) if text else regime
        views += [{**item, "text": ch} for ch in stages.chunks(text, 12000) if re.search(r"qubit", ch, re.I)]
    m1 = m2 = None
    kind = "attack"
    for n, view in enumerate(views):
        ex1, m1v = llm.call_chain("primary", lambda mod: stages.extract(view, mod))
        v1 = _verified(ex1, view, regime)
        m1 = m1v or m1
        kind = v1["kind"] if v1["kind"] in ("attack", "hardware") else kind
        if n == 0:
            rec["trail"]["primary"] = {"model": m1v, "extraction": ex1, "estimates": v1["estimates"]}
        needs = [e for e in v1["ok_estimates"] if v1["kind"] == "hardware" or router.is_frontier(e["values"], rows)]
        v2, m2v = None, None
        if needs:
            ex2, m2v = llm.call_chain("secondary", lambda mod: stages.extract(view, mod), exclude=m1v)
            v2 = _verified(ex2, view, regime)
            m2 = m2v or m2
            if n == 0:
                rec["trail"]["secondary"] = {"model": m2v, "extraction": ex2, "estimates": v2["estimates"]}
            unconfirmed = [e for e in needs if not any_agrees(e["values"], v2["ok_estimates"])]
            if m2v != llm.CHAINS["secondary"][0] and unconfirmed:
                # The second opinion came from a fallback model: retry later instead of demoting a good row for good.
                raise llm.LLMError(f"second opinion came from fallback model {m2v}, retrying later")
        independent = bool(m2v) and m2v != m1v  # a different model; the family is logged so this can be tightened later
        v3 = None
        if v2 and any(not any_agrees(e["values"], v2["ok_estimates"]) for e in needs):
            try:  # a rare tie-break: a third model, different from both, so that two of three can agree
                ex3, m3 = llm.call_chain("escalation", lambda mod: stages.extract(view, mod))
                if m3 not in (m1v, m2v):
                    v3 = _verified(ex3, view, regime)
            except llm.LLMError:
                v3 = None  # no tie-break available: the estimate stays unconfirmed
        for e in v1["estimates"]:
            second = independent and e["ok"] and (any_agrees(e["values"], v2["ok_estimates"] if v2 else [])
                                                  or bool(v3 and any_agrees(e["values"], v3["ok_estimates"])))
            tier, why = router.route(v1["kind"], e["ok"], e["values"], second, rows)
            if v2 and not independent and tier == "A":
                tier, why = "B", "second opinion came from the same model as the first"
            rec["estimates"].append({"kind": v1["kind"], "values": e["values"], "quote": e["quote"], "tier": tier, "reason": why,
                                     "regex_agrees": e["ok"] and any_agrees(e["values"], rx_v["ok_estimates"]),
                                     "view": "abstract" if n == 0 else f"full text, part {n}"})
    rec["trail"]["regex_agrees_any"] = any(e["regex_agrees"] for e in rec["estimates"])
    rec["estimates"] = dedupe_estimates(rec["estimates"])
    order = {"A": 0, "B": 1, "drop": 2}
    best = min(rec["estimates"], key=lambda x: order[x["tier"]], default=None)
    rec["tier"], rec["reason"] = (best["tier"], best["reason"]) if best else ("drop", "no estimates")
    rec["models"] = {"primary": m1, "secondary": m2, "different_family": bool(m2) and llm.family(m1) != llm.family(m2)}
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
        check_canary: bool = True, fulltext: bool = False):
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
            rec = process(it, rows["attack"], use_llm, fulltext)
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
    (DATA / ROWS["attack"]).write_text("[]")  # only the paper baseline is rebuilt; vendor hardware rows are never touched here
    return run(items=items, max_auto=10**6, check_canary=False, fulltext=True)


STALE_HOURS = 25  # the main run is daily; older than this means a run failed or lost its data


def _hours_since(iso):
    try:
        return (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(iso)).total_seconds() / 3600
    except (TypeError, ValueError):
        return float("inf")


def retry():
    """The frequent self-healing pass. Cheap when nothing is wrong.

    - Papers: a full pass if the last main run reported fetch errors or is older than STALE_HOURS (a failed or lost
      run); otherwise only the queued papers whose model calls failed.
    - Vendor pages: always re-checked. Unchanged pages cost one download and no model call.
    """
    status = _load(DATA / "status.json", {})
    queue = _load(DATA / "queue.json", {})
    out = {}
    if status.get("source_errors") or _hours_since(status.get("run_at")) > STALE_HOURS:
        out["reason"] = "last main run had fetch errors or is stale: running a full pass"
        out["papers"] = run(fulltext=True)
    elif queue:
        out["reason"] = "retrying queued papers"
        out["papers"] = run(items=[], fulltext=True)
    else:
        out["reason"] = "nothing queued"
    out["hardware"] = run_hardware()
    return out


MAX_HW_ROWS_PER_RUN = 25  # a burst larger than this is held for a person instead of applied


def _hw_key(v: dict):
    return (v.get("actor"), v.get("target_year"), v.get("physical_qubits"), v.get("logical_qubits"))


def run_hardware(items: list | None = None, dry: bool = False):
    """Fetch the configured vendor pages, extract roadmap claims (qubit count plus year) with two models,
    verify every quote against the page text, and append the claims both models agree on.

    Append-only: a vendor later removing or delaying a claim is not applied automatically.
    """
    errors = {}
    if items is None:
        items = []
        for src in _load(DATA / "hardware_sources.json", []):
            try:
                items += sources.fetch_pages([src])
            except RuntimeError as e:
                errors[src["url"]] = str(e)[:120]
    seen = _load(DATA / "hw_seen.json", {})
    rows = _load(DATA / "hardware.json", [])
    known = {_hw_key(r) for r in rows}
    summary = {"pages": len(items), "changed": 0, "applied": 0, "held": 0, "unavailable": 0, "errors": errors}
    new = []
    for it in items:
        if seen.get(it["id"]) == it["version"]:
            continue
        summary["changed"] += 1
        found, complete = [], True
        for chunk in stages.chunks(it["text"]):
            sub = {**it, "text": chunk}
            try:
                ex1, m1 = llm.call_chain("primary", lambda mod: stages.extract_hardware(sub, mod))
                v1 = verify(ex1, stages.source_text(sub), sources.is_allowlisted(it["url"]), {"actor": it["actor"]})
                if not v1["ok_estimates"]:
                    continue
                ex2, m2 = llm.call_chain("secondary", lambda mod: stages.extract_hardware(sub, mod), exclude=m1)
                v2 = verify(ex2, stages.source_text(sub), sources.is_allowlisted(it["url"]), {"actor": it["actor"]})
            except llm.LLMError:
                complete = False
                break
            for e in v1["ok_estimates"]:
                if any_agrees(e["values"], v2["ok_estimates"]):
                    found.append({"values": e["values"], "quote": e["quote"], "models": {"primary": m1, "secondary": m2}})
        if not complete:
            summary["unavailable"] += 1  # leave the page unseen so the next run tries again
            continue
        seen[it["id"]] = it["version"]
        for n, f in enumerate(dedupe_estimates(found)):
            if _hw_key(f["values"]) in known:
                continue
            known.add(_hw_key(f["values"]))
            vals = {k: (round(v, 6) if isinstance(v, float) else v) for k, v in f["values"].items()}
            new.append({"id": f"{it['id']}#{n}", "kind": "hardware", **vals, "quote": f["quote"], "url": it["url"],
                        "title": it["title"], "added": dt.date.today().isoformat(), "models": f["models"],
                        "verification": "auto: verifier + two models agree"})
    if len(new) > MAX_HW_ROWS_PER_RUN:
        summary["held"] = len(new)
        if not dry:
            (DATA / "proposals").mkdir(parents=True, exist_ok=True)
            (DATA / "proposals" / f"hardware_{dt.date.today().isoformat()}.json").write_text(json.dumps(new, indent=1))
        new = []
    summary["applied"] = len(new)
    if not dry:
        (DATA / "hardware.json").write_text(json.dumps(rows + new, indent=1))
        (DATA / "hw_seen.json").write_text(json.dumps(seen, indent=1))
    return summary
