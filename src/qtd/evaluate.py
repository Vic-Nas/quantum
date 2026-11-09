"""Trust measurement: score regex and each model against a hand-checked gold set.

Gold file: JSON lines {id, title, text, relevant, kind, estimates: [{target, physical_qubits, ...}]}
with numeric values in the units the verifier produces (runtime in hours).
"""
import json
import sys
from pathlib import Path

from . import llm, regex_extract, stages
from .prefilter import prefilter
from .verify import any_agrees, verify


def _match(got: dict, want: dict) -> bool:
    """Every field the gold lists must equal the extracted value (floats to tolerance)."""
    for k, w in want.items():
        g = got.get(k)
        if g is None:
            return False
        if isinstance(w, (int, float)) and isinstance(g, (int, float)):
            if abs(g - w) > 1e-6 * max(1.0, abs(w)):
                return False
        elif g != w:
            return False
    return True


def _compatible(got: dict, want: dict) -> bool:
    """Same target and no shared numeric field that conflicts."""
    if got.get("target") != want.get("target"):
        return False
    shared = {k: want[k] for k in want if k in got}
    return _match(got, shared)


def _score(method, gold, fn):
    s = {"method": method, "gold_estimates": 0, "found": 0, "accepted": 0, "accepted_correct": 0,
         "irrelevant_items": 0, "irrelevant_with_accepted": 0, "errors": 0}
    outs = {}
    for g in gold:
        try:
            ex = fn(g)
        except llm.LLMError:
            s["errors"] += 1
            continue
        v = verify(ex, f"{g['title']} {g['text']}")
        acc = [e["values"] for e in v["ok_estimates"]]
        outs[g["id"]] = v["ok_estimates"]
        if not g["relevant"]:
            s["irrelevant_items"] += 1
            s["irrelevant_with_accepted"] += int(bool(acc))
            continue
        for want in g["estimates"]:
            s["gold_estimates"] += 1
            s["found"] += int(any(_match(a, want) for a in acc))
        for a in acc:
            s["accepted"] += 1
            s["accepted_correct"] += int(any(_compatible(a, w) for w in g["estimates"]))
    s["recall"] = round(s["found"] / s["gold_estimates"], 3) if s["gold_estimates"] else None
    s["precision_of_accepted"] = round(s["accepted_correct"] / s["accepted"], 3) if s["accepted"] else None
    s["false_accepts"] = s["accepted"] - s["accepted_correct"]
    return s, outs


def run(gold_path="data/gold/gold.jsonl", use_llm=True):
    gold = [json.loads(l) for l in Path(gold_path).read_text().splitlines() if l.strip()]
    rel = [g for g in gold if g["relevant"]]
    irr = [g for g in gold if not g["relevant"]]
    report = {"n_items": len(gold), "n_relevant": len(rel), "n_gold_estimates": sum(len(g["estimates"]) for g in rel),
              "prefilter": {"recall": round(sum(prefilter(g)["keep"] for g in rel) / max(1, len(rel)), 3),
                            "irrelevant_passed": f"{sum(prefilter(g)['keep'] for g in irr)}/{len(irr)}"},
              "methods": []}
    rx_s, rx_o = _score("regex", gold, lambda g: regex_extract.extract(f"{g['title']}. {g['text']}"))
    report["methods"].append(rx_s)
    outs = {"regex": rx_o}
    if use_llm:
        report["coarse_filter"] = {}
        for label in ("primary", "secondary"):
            model = llm.MODELS[label]
            s, o = _score(f"llm:{label}:{model}", gold, lambda g, m=model: stages.extract(g, m))
            report["methods"].append(s)
            outs[label] = o
        flags = {}
        for g in gold:
            try:
                flags[g["id"]] = stages.coarse(g, llm.MODELS["coarse"]).get("relevant")
            except llm.LLMError:
                flags[g["id"]] = None
        report["coarse_filter"] = {
            "recall": round(sum(bool(flags[g["id"]]) for g in rel) / max(1, len(rel)), 3),
            "irrelevant_passed": f"{sum(bool(flags[g['id']]) for g in irr)}/{len(irr)}"}
        for a, b in (("primary", "secondary"), ("regex", "primary")):
            n = ag = 0
            for g in rel:
                for e in outs[a].get(g["id"], []):
                    n += 1
                    ag += int(any_agrees(e["values"], outs[b].get(g["id"], [])))
            report[f"agree_{a}_with_{b}"] = f"{ag}/{n} accepted estimates of {a} confirmed by {b}"
    return report


if __name__ == "__main__":
    print(json.dumps(run(use_llm="--no-llm" not in sys.argv), indent=1))
