"""When could it break? Pure, deterministic, no models.

For a target, the requirement is the cheapest published attack and the supply is the vendors' announced
machines. The earliest announced path is the first year an announced machine is at least that large.
Roadmap targets count as announced (the goal is pessimistic), and every result names its evidence.
"""

METRICS = ("physical_qubits", "logical_qubits")


def requirement(rows, target, metric):
    """Cheapest published requirement for a target in one metric, as the row that states it, or None."""
    cands = [r for r in rows if r.get("target") == target and r.get(metric) is not None]
    return min(cands, key=lambda r: (r[metric], r.get("published", ""))) if cands else None


def when(h) -> float:
    """When a machine is due, as a year fraction: the end of its month, or the end of its year if no month is given."""
    month = h.get("target_month")
    return int(h["target_year"]) + (int(month) / 12 if month else 1.0)


def pos(h) -> float:
    """Where to draw a machine on a time axis: the middle of its month, or the middle of its year."""
    month = h.get("target_month")
    return int(h["target_year"]) + ((int(month) - 0.5) / 12 if month else 0.5)


def earliest_path(attack_rows, hardware_rows, target):
    """Earliest announced path to break `target`, or a dict explaining why there is none.

    Returns {'year', 'month', 'when', 'metric', 'need', 'demand', 'supply'} or {'year': None, 'reason': ...}.
    `when` is the due date as a year fraction (the month is used when the source gives one).
    Physical-qubit figures from different hardware types are not strictly comparable; the caller shows that caveat.
    """
    best, any_need = None, False
    for metric in METRICS:
        need = requirement(attack_rows, target, metric)
        if not need:
            continue
        any_need = True
        ok = [h for h in hardware_rows if h.get(metric) is not None and h.get("target_year") is not None
              and h[metric] >= need[metric]]
        if not ok:
            continue
        h = min(ok, key=lambda r: (when(r), r[metric]))
        month = h.get("target_month")
        cand = {"year": int(h["target_year"]), "month": int(month) if month else None, "when": when(h), "metric": metric,
                "need": need[metric], "demand": need, "supply": h}
        if best is None or cand["when"] < best["when"]:
            best = cand
    if best:
        return best
    if not any_need:
        return {"year": None, "reason": "no published requirement"}
    if not hardware_rows:
        return {"year": None, "reason": "no hardware announcements collected"}
    return {"year": None, "reason": "no announced machine is large enough yet"}


def supply_points(hardware_rows, metric):
    """Announced machines in one metric as (year, value, row), with `record` marking each new largest-so-far."""
    pts = sorted(((int(h["target_year"]), h[metric], h) for h in hardware_rows
                  if h.get(metric) is not None and h.get("target_year") is not None), key=lambda p: (when(p[2]), p[1]))
    best, out = None, []
    for year, val, h in pts:
        rec = best is None or val > best
        best = val if rec else best
        out.append({"year": year, "x": pos(h), "y": val, "row": h, "record": rec})
    return out
