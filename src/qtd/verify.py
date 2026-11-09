"""Code-only verification. Each estimate is one verbatim quote plus fields found inside it."""
from .schema import CORE, FIELDS, MAX_QUOTE
from .textutil import (TARGET_IDS, all_targets, bits_row_for, canonical_target, infer_table_target, norm, number_followed_by,
                       numbers_in, parse_hours, parse_number, repair_quote)


def _close(a, b, rel=1e-9):
    return abs(a - b) <= rel * max(1.0, abs(a), abs(b))


AGREE_TOLERANCE = 0.03  # a title may say 22,593 where the abstract says "about 23,000": same result


def verify_estimate(kind: str, est: dict, src: str, allowlisted: bool = True, defaults: dict | None = None,
                    regime: str | None = None, context: str = "") -> dict:
    """Check one estimate {'quote', 'fields': {name: value_string}}."""
    quote = norm(est.get("quote", ""))
    fields = dict(est.get("fields") or {})
    if quote and quote.lower() not in src:  # a model joined passages with '...': keep the segment that is really in the source
        quote = repair_quote(quote, src, [str(v) for v in fields.values()])
    spec = FIELDS[kind]
    stated = str(fields.get("target") or "")
    if kind == "attack" and canonical_target(stated) is None and stated.strip().lower() not in TARGET_IDS:
        # an unlabeled table row, or a target that is not a recognisable algorithm: code, not the model, infers it
        inferred = infer_table_target(quote, context)
        if inferred:
            fields["target"] = inferred
    if regime == "logical" and "physical_qubits" in fields and "logical_qubits" not in fields and "physical" not in quote.lower():
        fields["logical_qubits"] = fields.pop("physical_qubits")  # in a logical-only paper an unlabeled '#qubits' is logical
    checks = {"source_allowlisted": allowlisted,
              "quote_verbatim": bool(quote) and quote.lower() in src,
              "quote_short": 0 < len(quote) <= MAX_QUOTE}
    values = {}
    for name, raw in fields.items():
        raw = str(raw).strip()
        if name not in spec:
            checks[f"{name}:known_field"] = False
            continue
        ftype, lo, hi = spec[name]
        if ftype == "target":
            canon = canonical_target(raw) or (str(raw).strip().lower() if str(raw).strip().lower() in TARGET_IDS else None)
            checks[f"{name}:in_quote"] = canon is not None and (canon in all_targets(quote) or bits_row_for(canon, quote, context))
            values[name] = canon
        elif ftype == "text":
            checks[f"{name}:in_quote"] = bool(raw) and raw.lower() in quote.lower()
            values[name] = raw
        elif ftype == "duration":
            hrs = parse_hours(raw)
            checks[f"{name}:in_quote"] = hrs is not None and hrs in [parse_hours(quote[i:]) for i in range(len(quote))]
            checks[f"{name}:in_bounds"] = hrs is not None and lo <= hrs <= hi
            values[name] = hrs
        else:
            val = parse_number(raw)
            checks[f"{name}:in_quote"] = val is not None and any(_close(val, n) for n in numbers_in(quote))
            checks[f"{name}:in_bounds"] = val is not None and lo <= val <= hi
            if name.endswith("_qubits"):  # a count of qubits is a whole number; '212.6' is a lost exponent
                checks[f"{name}:whole_number"] = val is not None and abs(val - round(val)) < 1e-9
            if name == "logical_qubits":  # a count is only 'logical' if the source says so
                checks[f"{name}:says_logical"] = "logical" in quote.lower() or (regime == "logical" and "physical" not in quote.lower())
            if name == "physical_qubits" and regime == "logical":  # in a logical-only paper, 'physical' must be said outright
                checks[f"{name}:says_physical"] = "physical" in quote.lower()
            if name == "physical_qubits" and val is not None:  # ... and not 'physical' when the source calls it logical
                checks[f"{name}:not_logical"] = not number_followed_by(quote, val, r"(?:error[\s-]corrected\s+)?logical")
            values[name] = val
    # A figure that fails is dropped, never allowed to sink the estimate (dropping loses information, it cannot invent any).
    # The algorithm itself (target or actor) is the exception: if that fails the estimate is rejected.
    for name in [n for n in list(values) if n not in ("target", "actor")]:
        if any(not ok for key, ok in checks.items() if key.startswith(name + ":")):
            for key in [k for k in checks if k.startswith(name + ":")]:
                del checks[key]
            values.pop(name, None)
    for k, v in (defaults or {}).items():  # e.g. the vendor of a configured page
        values.setdefault(k, v)
    core = CORE[kind]
    checks["has_core"] = bool(values.get(core)) and len(values) > 1
    if kind == "attack":  # an attack estimate is only useful with a qubit count
        checks["has_size"] = values.get("physical_qubits") is not None or values.get("logical_qubits") is not None
    if kind == "hardware":  # a roadmap claim needs a year and a qubit count, otherwise it cannot be placed in time
        checks["has_year_and_size"] = values.get("target_year") is not None and (
            values.get("physical_qubits") is not None or values.get("logical_qubits") is not None)
    return {"ok": all(checks.values()), "checks": checks, "values": values, "quote": quote}


def verify(extraction: dict, source_text: str, allowlisted: bool = True, defaults: dict | None = None,
           regime: str | None = None, context: str = "") -> dict:
    """Verify every estimate. Returns {'kind', 'estimates': [per-estimate result], 'ok_estimates': [...]}."""
    kind = extraction.get("kind")
    if kind not in FIELDS:
        return {"kind": kind, "estimates": [], "ok_estimates": []}
    src = norm(source_text).lower()
    res = [verify_estimate(kind, e, src, allowlisted, defaults, regime, context) for e in extraction.get("estimates", [])]
    return {"kind": kind, "estimates": res, "ok_estimates": [r for r in res if r["ok"]]}


def agree(a: dict, b: dict) -> bool:
    """Two value dicts agree if they share a core field and every shared field matches."""
    shared = set(a) & set(b)
    # Need the same subject AND at least one measured field in common, or agreement is vacuous.
    if not ({"target", "actor"} & shared) or len(shared) < 2:
        return False
    # The second opinion must itself state every size and year the first one gave. A figure it could not support
    # was dropped by the verifier, and a dropped figure is not a confirmation.
    if any(k in a and k not in b for k in ("physical_qubits", "logical_qubits", "target_year")):
        return False
    for k in shared:
        x, y = a[k], b[k]
        if isinstance(x, float) and isinstance(y, float):
            if not _close(x, y, AGREE_TOLERANCE):
                return False
        elif x != y:
            return False
    return True


def any_agrees(values: dict, others: list) -> bool:
    """True if some verified estimate in `others` agrees with `values`."""
    return any(agree(values, o["values"]) for o in others)
