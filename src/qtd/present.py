"""Pure presentation helpers: formatting and summaries. No I/O, so they are unit-tested directly."""
import re

TARGET_LABELS = {
    "rsa-2048": ("RSA-2048", "TLS certificates, code signing, older PGP keys"),
    "rsa-3072": ("RSA-3072", ""),
    "rsa-4096": ("RSA-4096", ""),
    "ecdlp-256": ("256-bit elliptic curve", "secp256k1, P-256, Curve25519, Ed25519"),
    "ecdlp-384": ("384-bit elliptic curve", "P-384"),
    "dlp-ffdhe-2048": ("2048-bit finite-field DH", "ffdhe2048"),
    "dlp-ff-512": ("512-bit finite-field discrete log", "smaller than the sizes in use"),
    "aes-128": ("AES-128", "key search with Grover's algorithm"),
    "aes-256": ("AES-256", "key search with Grover's algorithm"),
    "sha-256": ("SHA-256", "pre-image search with Grover's algorithm"),
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


def year_label(year, month=None) -> str:
    """'2028' or 'Mar 2028' when month precision is available."""
    y = int(year)
    if month is not None:
        m = int(month)
        if 1 <= m <= 12:
            return f"{_MONTHS[m - 1]} {y}"
    return str(y)


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


# Hand-written (not extracted): the algorithms people actually use that a large quantum computer affects.
# status: "broken" = Shor's algorithm recovers the key; "weakened" = Grover's algorithm halves the security level.
# target: which data to show (a pairing curve is attacked as an elliptic curve over a field of about that size).
ALGORITHMS = [
    ("RSA (2048, 3072, 4096 bits)", "HTTPS certificates, signed software and updates, older PGP email, some VPNs", "broken", "rsa-2048", "2048-bit shown"),
    ("secp256k1 (ECDSA)", "Bitcoin, Ethereum and most other blockchains", "broken", "ecdlp-256", ""),
    ("P-256 (secp256r1)", "HTTPS, passkeys, many corporate systems", "broken", "ecdlp-256", ""),
    ("Curve25519, X25519 and Ed25519", "SSH keys, Signal, WireGuard, modern HTTPS key exchange, Tor", "broken", "ecdlp-256", ""),
    ("P-384 and larger curves", "Government and enterprise HTTPS, some code signing", "broken", "ecdlp-384", "384-bit shown"),
    ("Finite-field Diffie-Hellman and DSA", "Older HTTPS, SSH and VPN setups", "broken", "dlp-ff-512", "512-bit field shown; real keys are larger"),
    ("BLS12-381 and BN254 pairing curves", "Ethereum validator signatures, zero-knowledge proofs, KZG commitments", "broken", "ecdlp-384",
     "attacked like a curve over a 381-bit field"),
    ("AES-128", "Disk and network encryption", "weakened", "aes-128", ""),
    ("SHA-256 and other hashes", "Bitcoin mining and addresses, certificates, passwords", "weakened", "sha-256", ""),
]
# Targets whose published figure is for a smaller size than the keys in use: the real date can only be later.
PROXY_TARGETS = {"dlp-ff-512"}
ALGORITHMS_NOTE = ("Broken: a large enough quantum computer recovers the secret key. Weakened: the security level is roughly halved, "
                   "so larger keys fix it. Replacements exist (NIST standardised ML-KEM, ML-DSA and SLH-DSA in 2024).")


_SUP = str.maketrans("0123456789-", "\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079\u207b")


def sci(n) -> str:
    """4.52e11 -> '4.5 x 10^11' using superscript digits; small numbers keep their commas."""
    if n is None:
        return ""
    if n < 1e6:
        return f"{n:,.0f}"
    exp = len(f"{int(n):d}") - 1
    return f"{n / 10 ** exp:.1f} \u00d7 10{str(exp).translate(_SUP)}"


# One line per attack on the single chart: (data target, short label, the algorithms it stands for, status).
CHART_GROUPS = [
    ("ecdlp-256", "256-bit curves", "secp256k1 (Bitcoin, Ethereum), P-256, Curve25519 and Ed25519", "broken"),
    ("rsa-2048", "RSA-2048", "RSA keys", "broken"),
    ("ecdlp-384", "P-384, BLS12-381", "P-384 and larger curves, and the BLS12-381 pairing curve", "broken"),
    ("dlp-ff-512", "Finite-field DH", "finite-field Diffie-Hellman and DSA (512-bit field shown)", "broken"),
    ("aes-128", "AES-128", "AES-128", "weakened"),
    ("sha-256", "SHA-256", "SHA-256 and other hashes", "weakened"),
]

# Hand-written: what a break would mean, for the groups SECURES does not cover.
CONSEQUENCE = {
    "ecdlp-384": "Government and enterprise connections and signed code could be forged, recorded traffic could be read later, and "
                 "Ethereum validator signatures (BLS12-381) could be forged.",
    "dlp-ff-512": "Older connections that use finite-field Diffie-Hellman could be decrypted. Real keys are larger than 512 bits, "
                  "so this is the earliest it could possibly happen.",
    "aes-128": "Not broken, only weakened: a quantum computer would need far too many steps in a row. Using AES-256 removes the concern.",
    "sha-256": "Not broken, only weakened: the attack needs an astronomically long chain of steps. Longer hash outputs remove the concern.",
}

# The countdown on the front page: what a newcomer cares about, in plain words. (title, what it covers, data targets).
COUNTDOWN = [
    ("Bitcoin, Ethereum and crypto wallets", "Also Signal, SSH and WireGuard logins: all use the same 256-bit curves", ["ecdlp-256"]),
    ("Websites and software updates", "RSA keys behind HTTPS certificates and signed code", ["rsa-2048"]),
    ("Government connections and Ethereum validators", "P-384 and BLS12-381", ["ecdlp-384"]),
    ("Older VPN and SSH setups", "Finite-field Diffie-Hellman. Real keys are bigger than the 512 bits studied, so later", ["dlp-ff-512"]),
    ("Disk encryption and passwords", "AES-128 and SHA-256 are only weakened, not broken", ["aes-128", "sha-256"]),
]

# Specific apps and services people recognize, mapped to which threat group they fall under.
# (name, short status note, threat_slug, pq_status)
# pq_status: "migrating" = adding post-quantum protection, "not yet" = still vulnerable, "partial" = some protection added
SERVICES = [
    ("Chrome / Firefox", "HTTPS uses RSA or ECC certificates", "websites", "migrating", "Browsers are adopting ML-KEM for key exchange, but certificates still use classic keys."),
    ("Signal", "X25519 key exchange (256-bit curve)", "bitcoin", "migrating", "Signal added PQXDH (post-quantum key agreement) in 2023. Older messages recorded before the update are still at risk."),
    ("iMessage", "P-256 key exchange", "bitcoin", "migrating", "Apple added PQ3 post-quantum protocol in 2024. Older messages recorded before the update are still at risk."),
    ("WhatsApp", "Curve25519 (Signal protocol)", "bitcoin", "not yet", "Uses the Signal protocol but has not yet enabled Signal's post-quantum upgrade."),
    ("Tor Browser", "Curve25519 for relay circuits", "bitcoin", "not yet", "Tor relays use X25519. A quantum computer could decrypt recorded traffic. Post-quantum relay handshakes are in development."),
    ("SSH", "Ed25519 or RSA keys", "bitcoin", "partial", "OpenSSH 9.0+ supports hybrid post-quantum key exchange, but most servers have not enabled it."),
    ("WireGuard", "Curve25519 key exchange", "bitcoin", "not yet", "WireGuard uses X25519. Recorded traffic could be decrypted later. No post-quantum option yet."),
    ("Bitcoin", "secp256k1 (ECDSA signatures)", "bitcoin", "not yet", "Coins whose public key is exposed on-chain are most at risk. No consensus on a migration plan yet."),
    ("Ethereum", "secp256k1 + BLS12-381 validators", "bitcoin", "not yet", "Wallet keys and validator signatures are both vulnerable. Account abstraction may help wallets migrate."),
    ("1Password / Bitwarden", "AES-256 vault, SRP or RSA key exchange", "disk-encryption", "partial", "Vault encryption (AES-256) is safe. Key exchange during login may use RSA or SRP, which is not."),
    ("VPN (OpenVPN, IPsec)", "RSA or DH key exchange", "older-vpn", "not yet", "Most VPN setups still use classic key exchange. Recorded traffic could be decrypted later."),
]
