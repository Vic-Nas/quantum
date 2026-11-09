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
    name = TARGET_SHARE[target] if target in TARGET_SHARE else label(target)[0]
    now = short_count(h["best"]["y"])
    if h["first"] is h["best"]:
        return f"{name}: {now} qubits needed"
    return f"{name}: {short_count(h['first']['y'])} \u2192 {now} qubits since {date_label(h['first']['date'], True)}"


TARGET_SHARE = {"ecdlp-256": "Bitcoin and Ethereum keys", "rsa-2048": "RSA-2048 (websites, software updates)"}


def home_card(rows, as_of, base_url, image_url=None):
    """Card for the home page. as_of is a date string like 2026-11-09 or ''."""
    parts = [s for s in (_sentence(rows, t) for t in TARGET_ORDER) if s]
    when = f" As of {clean(as_of, 10)}." if as_of else ""
    desc = ("Published estimates of the quantum computer size needed. " + ". ".join(parts) + "." + when) if parts \
        else "No estimates published yet."
    card = {"title": TITLE, "description": clean(desc, 250), "url": base_url, "type": "website",
            "image": None, "site_name": SITE_NAME, "theme_color": "#f4f1ea"}
    if image_url:
        card.update(image=image_url, image_width=1200, image_height=630,
                    image_alt="Qubits needed to break Bitcoin-grade keys and RSA-2048, then and now")
    return card


def default_card(base_url):
    return {"title": SITE_NAME, "description": DEFAULT_DESC, "url": base_url, "type": "website",
            "image": None, "site_name": SITE_NAME, "theme_color": "#f4f1ea"}
