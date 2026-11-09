"""Routing: Tier A (could move a headline, needs a human merge) vs Tier B (radar, never moves a date)."""
import json
from pathlib import Path

from .schema import COST_FIELDS


def load_rows(path="data/attacks.json"):
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else []


def is_frontier(values: dict, rows: list) -> bool:
    """True if this attack is cheaper than every known row for its target on any cost axis."""
    target = values.get("target")
    same = [r for r in rows if r.get("target") == target]
    if not same:
        return True
    for f in COST_FIELDS:
        v = values.get(f)
        if v is None:
            continue
        known = [r[f] for r in same if r.get(f) is not None]
        if not known or v < min(known):
            return True
    return False


def route(kind: str, verified_ok: bool, values: dict, second_agrees: bool, rows: list):
    """Return (tier, reason). Tier is 'A', 'B' or 'drop'."""
    if not verified_ok:
        return "drop", "failed verification"
    if kind == "hardware":
        return ("A", "hardware claim") if second_agrees else ("B", "hardware claim, no second-model agreement")
    if not is_frontier(values, rows):
        return "B", "verified but not cheaper than known estimates"
    if not second_agrees:
        return "B", "would move a date but second model disagrees or failed"
    return "A", "verified, frontier, two models agree"
