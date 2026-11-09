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


def clean(text, limit=None) -> str:
    """Strip control characters and newlines from untrusted text and optionally truncate."""
    t = re.sub(r"\s+", " ", _CTRL.sub(" ", str(text or ""))).strip()
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
