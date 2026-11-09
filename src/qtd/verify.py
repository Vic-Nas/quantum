"""Code-only verification. Each estimate is one verbatim quote plus fields found inside it."""
from .schema import CORE, FIELDS, MAX_QUOTE
from .textutil import all_targets, canonical_target, norm, numbers_in, parse_hours, parse_number


def _close(a, b, rel=1e-9):
    return abs(a - b) <= rel * max(1.0, abs(a), abs(b))


AGREE_TOLERANCE = 0.03  # a title may say 22,593 where the abstract says "about 23,000": same result


def verify_estimate(kind: str, est: dict, src: str, allowlisted: bool = True, defaults: dict | None = None) -> dict:
    """Check one estimate {'quote', 'fields': {name: value_string}}."""
    quote = norm(est.get("quote", ""))
    spec = FIELDS[kind]
    checks = {"source_allowlisted": allowlisted,
              "quote_verbatim": bool(quote) and quote.lower() in src,
              "quote_short": 0 < len(quote) <= MAX_QUOTE}
    values = {}
    for name, raw in (est.get("fields") or {}).items():
        raw = str(raw).strip()
        if name not in spec:
            checks[f"{name}:known_field"] = False
            continue
        ftype, lo, hi = spec[name]
        if ftype == "target":
            canon = canonical_target(raw)
            checks[f"{name}:in_quote"] = canon is not None and canon in all_targets(quote)
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
            values[name] = val
    for k, v in (defaults or {}).items():  # e.g. the vendor of a configured page
        values.setdefault(k, v)
    core = CORE[kind]
    checks["has_core"] = bool(values.get(core)) and len(values) > 1
    if kind == "hardware":  # a roadmap claim needs a year and a qubit count, otherwise it cannot be placed in time
        checks["has_year_and_size"] = values.get("target_year") is not None and (
            values.get("physical_qubits") is not None or values.get("logical_qubits") is not None)
    return {"ok": all(checks.values()), "checks": checks, "values": values, "quote": quote}


def verify(extraction: dict, source_text: str, allowlisted: bool = True, defaults: dict | None = None) -> dict:
    """Verify every estimate. Returns {'kind', 'estimates': [per-estimate result], 'ok_estimates': [...]}."""
    kind = extraction.get("kind")
    if kind not in FIELDS:
        return {"kind": kind, "estimates": [], "ok_estimates": []}
    src = norm(source_text).lower()
    res = [verify_estimate(kind, e, src, allowlisted, defaults) for e in extraction.get("estimates", [])]
    return {"kind": kind, "estimates": res, "ok_estimates": [r for r in res if r["ok"]]}


def agree(a: dict, b: dict) -> bool:
    """Two value dicts agree if they share a core field and every shared field matches."""
    shared = set(a) & set(b)
    # Need the same subject AND at least one measured field in common, or agreement is vacuous.
    if not ({"target", "actor"} & shared) or len(shared) < 2:
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
