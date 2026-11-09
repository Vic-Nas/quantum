"""Share-card wording. Plain values in, dict out, so it is tested without the site.

A card is a public snapshot: build it only from what the page shows to any visitor, and word
live figures as 'as of' facts (never relative times).
"""
from .present import TARGET_ORDER, clean, date_label, headline, label, short_count

SITE_NAME = "Quantum threat tracker"
TITLE = "How close is quantum computing to breaking encryption?"
DEFAULT_DESC = "Published estimates of how many qubits it takes to break RSA and elliptic curves, with the papers as proof."


def _sentence(rows, target):
    h = headline(rows, target)
    if not h:
        return ""
    name = label(target)[0]
    now = short_count(h["best"]["y"])
    if h["first"] is h["best"]:
        return f"{name} needs {now} qubits"
    return (f"{name} needed {short_count(h['first']['y'])} qubits in {date_label(h['first']['date'], True)[-4:]}"
            f" and now {now}")


def home_card(rows, as_of, base_url):
    """Card for the home page. as_of is a date string like 2026-11-09 or ''."""
    parts = [s for s in (_sentence(rows, t) for t in TARGET_ORDER) if s]
    when = f" (as of {clean(as_of, 10)})" if as_of else ""
    desc = ("; ".join(parts) + f", by published estimates{when}.") if parts else "No estimates published yet."
    return {"title": TITLE, "description": clean(desc, 250), "url": base_url, "type": "website",
            "image": None, "site_name": SITE_NAME, "theme_color": "#f4f1ea"}


def default_card(base_url):
    return {"title": SITE_NAME, "description": DEFAULT_DESC, "url": base_url, "type": "website",
            "image": None, "site_name": SITE_NAME, "theme_color": "#f4f1ea"}
