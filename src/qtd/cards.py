"""Share-card wording. Plain values in, dict out, so it is tested without the site.

A card is a public snapshot: build it only from what the page shows to any visitor, and word
live figures as 'as of' facts (never relative times).
"""
from .breakdate import earliest_path
from .present import TARGET_ORDER, clean, headline, label, short_count, year_label

SITE_NAME = "Quantum threat tracker"
TITLE = "How close is quantum computing to breaking encryption?"
DEFAULT_DESC = "Published estimates of how many qubits it takes to break RSA and elliptic curves, with the papers as proof."


TARGET_SHARE = {"ecdlp-256": "Bitcoin and Ethereum keys", "rsa-2048": "RSA-2048 (websites, software updates)"}


def _part(rows, hw_rows, target):
    name = TARGET_SHARE.get(target) or label(target)[0]
    path = earliest_path(rows, hw_rows, target)
    if path.get("year"):
        return f"{name} {year_label(path['year'], path.get('month'))}"
    h = headline(rows, target)
    if h:
        return f"{name}: no announced machine is big enough yet (needs {short_count(h['best']['y'])} qubits)"
    return ""


def home_card(rows, hw_rows, as_of, base_url, image_url=None):
    """Card for the home page. as_of is a date string like 2026-11-09 or ''."""
    parts = [x for x in (_part(rows, hw_rows, t) for t in TARGET_ORDER) if x]
    when = f" As of {clean(as_of, 10)}." if as_of else ""
    desc = ("Earliest announced path to a break, from vendor roadmaps vs the cheapest published attack: " + "; ".join(parts)
            + ". Plans, not delivered machines." + when) if parts else "No estimates published yet."
    card = {"title": TITLE, "description": clean(desc, 250), "url": base_url, "type": "website",
            "image": None, "site_name": SITE_NAME, "theme_color": "#f4f1ea"}
    if image_url:
        card.update(image=image_url, image_width=1200, image_height=630,
                    image_alt="Earliest announced year a quantum computer could break Bitcoin-grade keys and RSA-2048")
    return card


def default_card(base_url):
    return {"title": SITE_NAME, "description": DEFAULT_DESC, "url": base_url, "type": "website",
            "image": None, "site_name": SITE_NAME, "theme_color": "#f4f1ea"}
