"""Share-card wording. Plain values in, dict out, so it is tested without the site.

A card is a public snapshot: build it only from what the page shows to any visitor, and word
live figures as 'as of' facts (never relative times).
"""
from .present import best_by_target, clean, count, label

SITE_NAME = "Quantum threat tracker"
DEFAULT_DESC = "Published quantum resource estimates for breaking RSA and elliptic curves, with sources."


def home_card(rows, as_of, base_url):
    """Card for the home page. as_of is a date string like 2026-11-09 or ''."""
    best = best_by_target(rows)
    parts = []
    for target, b in best.items():
        if b["physical"]:
            parts.append(f"{label(target)[0]} {count(b['physical']['physical_qubits'])}")
    when = f"As of {clean(as_of, 10)}. " if as_of else ""
    if parts:
        desc = (f"{when}Fewest physical qubits published: " + "; ".join(parts[:3])
                + ". Every figure links to its source quote.")
    else:
        desc = when + "No estimates published yet."
    return {"title": "Cheapest known quantum attacks", "description": clean(desc, 250),
            "url": base_url, "type": "website", "image": None, "site_name": SITE_NAME,
            "theme_color": "#f4f1ea"}


def default_card(base_url):
    return {"title": SITE_NAME, "description": DEFAULT_DESC, "url": base_url, "type": "website",
            "image": None, "site_name": SITE_NAME, "theme_color": "#f4f1ea"}
