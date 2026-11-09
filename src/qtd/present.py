"""Pure presentation helpers: formatting and summaries. No I/O, so they are unit-tested directly."""
import re

TARGET_LABELS = {
    "rsa-2048": ("RSA-2048", "TLS certificates, code signing, older PGP keys"),
    "rsa-3072": ("RSA-3072", ""),
    "rsa-4096": ("RSA-4096", ""),
    "ecdlp-256": ("256-bit elliptic curve", "secp256k1, P-256, Curve25519, Ed25519"),
    "ecdlp-384": ("384-bit elliptic curve", "P-384"),
    "dlp-ffdhe-2048": ("2048-bit finite-field DH", "ffdhe2048"),
    "pairing-bls12-381": ("BLS12-381", ""),
    "pairing-bn254": ("BN254", ""),
}
_CTRL = re.compile(r"[\x00-\x1f\x7f]+")
# Em dashes (and spaced en dashes or ' -- ') read as an AI tic. Replace with '; '. Unspaced en dashes (ranges like 2019-2026) stay.
_DASH = re.compile(r"\s*\u2014\s*|\s+\u2013\s+|\s+--+\s+")


def strip_dashes(text) -> str:
    return _DASH.sub("; ", str(text or ""))


def clean(text, limit=None) -> str:
    """Strip control characters and newlines from untrusted text and optionally truncate."""
    t = re.sub(r"\s+", " ", _CTRL.sub(" ", strip_dashes(text))).strip()
    if limit and len(t) > limit:
        t = t[: limit - 1].rstrip() + "…"
    return t


def label(target: str):
    return TARGET_LABELS.get(target, (clean(target) or "Unknown", ""))


def count(n) -> str:
    return "" if n is None else f"{n:,.0f}"


def duration(hours) -> str:
    if hours is None:
        return ""
    if hours < 1:
        m = hours * 60
        return f"{m:.0f} minutes" if m != 1 else "1 minute"
    if hours < 48:
        h = round(hours, 2)
        return "1 hour" if h == 1 else f"{h:g} hours"
    d = f"{hours / 24:.1f}".rstrip("0").rstrip(".")
    return f"{d} days"


def best_by_target(rows):
    """Per target: the row with the fewest physical qubits and the row with the fewest logical qubits."""
    out = {}
    for r in rows:
        t = out.setdefault(r.get("target"), {"physical": None, "logical": None, "n": 0})
        t["n"] += 1
        p, lq = r.get("physical_qubits"), r.get("logical_qubits")
        if p is not None and (t["physical"] is None or p < t["physical"]["physical_qubits"]):
            t["physical"] = r
        if lq is not None and (t["logical"] is None or lq < t["logical"]["logical_qubits"]):
            t["logical"] = r
    return dict(sorted(out.items(), key=lambda kv: str(kv[0])))


def paper_id(row_id: str) -> str:
    """'arxiv:2609.05625#4' -> 'arXiv 2609.05625'; 'eprint:2026/123#0' -> 'ePrint 2026/123'."""
    base = str(row_id).split("#")[0]
    kind, _, rest = base.partition(":")
    return f"{ {'arxiv': 'arXiv', 'eprint': 'ePrint'}.get(kind, clean(kind)) } {clean(rest)}".strip()


_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def short_count(n) -> str:
    """Plain-language count: 20000000 -> '20 million', 45000 -> '45,000'."""
    if n is None:
        return ""
    if n >= 1e6:
        return f"{n / 1e6:.1f}".rstrip("0").rstrip(".") + " million"
    return f"{n:,.0f}"


def date_label(iso: str, short: bool = False) -> str:
    """'2026-10-27' -> '27 Oct 2026' (or 'Oct 2026' when short)."""
    try:
        y, m, d = (int(x) for x in str(iso)[:10].split("-"))
        return f"{_MONTHS[m - 1]} {y}" if short else f"{d} {_MONTHS[m - 1]} {y}"
    except (ValueError, IndexError):
        return ""


def year_frac(iso: str):
    try:
        y, m, d = (int(x) for x in str(iso)[:10].split("-"))
        return y + (m - 1) / 12 + (d - 1) / 365
    except ValueError:
        return None


def dom_id(row_id: str) -> str:
    return "p-" + re.sub(r"[^a-z0-9]+", "-", str(row_id).lower()).strip("-")


def series(rows, target):
    """Plottable points for a target: physical-qubit estimates with a paper date, oldest first.

    Each point gets `record` True if it set a new lowest value so far (the 'best known' staircase).
    """
    pts = []
    for r in rows:
        if r.get("target") != target or r.get("physical_qubits") is None:
            continue
        x = year_frac(r.get("published", ""))
        if x is not None:
            pts.append({"row": r, "x": x, "y": r["physical_qubits"], "date": r["published"][:10]})
    pts.sort(key=lambda p: (p["x"], -p["y"]))
    best = None
    for p in pts:
        p["record"] = best is None or p["y"] < best
        best = p["y"] if p["record"] else best
    return pts


def headline(rows, target):
    """First and current-best published physical-qubit estimate for a target, or None."""
    pts = series(rows, target)
    if not pts:
        return None
    first = pts[0]
    best = min(pts, key=lambda p: (p["y"], -p["x"]))
    drop = 1 - best["y"] / first["y"] if first is not best and first["y"] else 0
    return {"first": first, "best": best, "drop_pct": round(drop * 100, 1), "n": len(pts)}


TARGET_PLAIN = {
    "rsa-2048": "Protects secure websites, software updates and older encrypted email.",
    "ecdlp-256": "Signs Bitcoin and Ethereum transactions. Also used by secure web connections, SSH, Signal and WireGuard.",
}
TARGET_ORDER = ["ecdlp-256", "rsa-2048"]


# What people recognise, and the technical name underneath.
TARGET_NAMES = {
    "ecdlp-256": ("Bitcoin, Ethereum and secure logins", "256-bit elliptic curves"),
    "rsa-2048": ("Websites and software updates", "RSA-2048"),
}
# Hand-written (not extracted): what each algorithm protects and what a break would mean.
SECURES = {
    "ecdlp-256": [
        ("Bitcoin and Ethereum",
         "Owning coins means holding a private key. Breaking the curve lets an attacker work out that key from its public key "
         "and move the coins. The most exposed coins are those whose public key is already visible on the blockchain."),
        ("Secure connections, SSH and messaging",
         "TLS, SSH, Signal and WireGuard use these curves. Traffic recorded today could be decrypted later, and logins or "
         "identities could be forged. Many of them have started adding post-quantum protection."),
    ],
    "rsa-2048": [
        ("Websites (HTTPS certificates)",
         "A certificate proves a site is the real one. A broken key would let an attacker build fake sites that browsers trust."),
        ("Software updates and signed code",
         "Updates are signed so devices can trust them. A broken key would let malicious software look official."),
        ("Older encrypted email and files",
         "Messages encrypted with RSA and recorded today could be read once the key can be broken."),
    ],
}
SECURES_NOTE = "Replacements exist: NIST standardised post-quantum schemes in 2024. The risk is systems that have not switched yet."


def plain_reason(reason: str) -> str:
    r = str(reason or "")
    if "second model" in r or "second opinion" in r:
        return "A second AI model could not confirm the numbers."
    if "failed verification" in r:
        return "A number or quote did not match the paper's text."
    if "models unavailable" in r:
        return "The AI models were unavailable when it was checked."
    return clean(r, 120)
