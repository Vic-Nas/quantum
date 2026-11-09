"""Plain-code helpers: number, duration and target parsing. No models involved."""
import re

_MULT = {"thousand": 1e3, "k": 1e3, "million": 1e6, "billion": 1e9, "trillion": 1e12}
_WORDNUM = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
            "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}

NUM_RE = re.compile(
    r"(?P<num>\d{1,3}(?:[,\u202f\u00a0 ]\d{3})+(?!\d)(?:\.\d+)?|\d+(?:\.\d+)?|\ba\b|\ban\b|\bone\b|\btwo\b"
    r"|\bthree\b|\bfour\b|\bfive\b|\bsix\b|\bseven\b|\beight\b|\bnine\b|\bten\b)"
    r"(?:\s*(?:[x*\u00d7]|\\times|\\cdot|\u22c5)\s*10\^?\{?(?P<exp>-?\d+)\}?)?"
    r"(?:\s*(?P<mult>thousand|million|billion|trillion)\b|(?P<k>k)\b)?",
    re.I,
)


_TEXMACRO = re.compile(r"\\(?:mathtt|mathrm|texttt|text|mathbf|textbf|mathit|textit)\{([^{}]*)\}")


def norm(text: str) -> str:
    """Normalise whitespace, unicode and LaTeX markup so quotes match verbatim.

    Applied identically to source and quote, so it only removes markup, never adds content.
    """
    t = (text or "").replace("\u2010", "-").replace("\u2011", "-").replace("\u2013", "-")
    t = t.replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    t = _TEXMACRO.sub(r"\1", t)
    t = t.replace("\\cdot", "\u00d7").replace("\\times", "\u00d7").replace("\u22c5", "\u00d7").replace("*", "\u00d7")
    t = t.replace("\\%", "%").replace("\\,", " ").replace("\\;", " ").replace("$", "")
    t = re.sub(r"\s*\u00d7\s*", "\u00d7", t)
    return re.sub(r"\s+", " ", t).strip()


def numbers_in(text: str):
    """Yield every numeric value in text, resolving 'a million', '1.2 million', '1,000,000'."""
    out = []
    for m in NUM_RE.finditer(text or ""):
        raw = re.sub(r"[,\u202f\u00a0 ]", "", m.group("num").lower())
        if raw in _WORDNUM:
            if not m.group("mult"):
                continue  # bare 'a' / 'one' is not a quantity unless scaled
            val = float(_WORDNUM[raw])
        else:
            val = float(raw)
        if m.group("exp"):
            val *= 10 ** int(m.group("exp"))
        if m.group("mult"):
            val *= _MULT[m.group("mult").lower()]
        elif m.group("k"):
            val *= 1e3
        out.append(val)
    return out


def parse_number(text: str):
    """Parse a model-provided value string into a float, or None."""
    ns = numbers_in(text or "")
    if ns:
        return ns[0]
    try:
        return float(str(text).replace(",", ""))
    except (TypeError, ValueError):
        return None


_UNIT_H = {"minute": 1 / 60, "hour": 1, "day": 24, "week": 168, "month": 730, "year": 8760}
_UNITS = r"(?P<u>minutes?|mins?|hours?|hrs?|h|days?|d|weeks?|wks?|months?|years?|yrs?)\b"
DUR_RE = re.compile(
    r"\b(?:(?P<n>\d+(?:\.\d+)?)\s*(?:-)?|(?P<w>a|an|one|two|three|four|five|six|seven|eight|nine|ten)[\s-]+)" + _UNITS,
    re.I,
)


def _unit(u: str) -> float:
    u = u.lower()
    if u.startswith("mo"):
        return _UNIT_H["month"]
    for prefix, key in (("mi", "minute"), ("h", "hour"), ("d", "day"), ("w", "week"), ("y", "year")):
        if u.startswith(prefix):
            return _UNIT_H[key]
    raise ValueError(u)


def parse_hours(text: str):
    """Parse a duration like 'less than a week', '8 days' or '9 h' into hours, or None."""
    m = DUR_RE.search(text or "")
    if not m:
        return None
    n = float(m.group("n")) if m.group("n") else _WORDNUM[m.group("w").lower()]
    return n * _unit(m.group("u"))


# Canonical targets. Cost depends on family and size, so a paper updates a family.
_TARGETS = [
    ("rsa-2048", r"\brsa[\s-]*2048\b|\b2048[\s-]*bit\s+(?:rsa\b|integers?|moduli|modulus)"),
    ("rsa-3072", r"\brsa[\s-]*3072\b|\b3072[\s-]*bit\s+(?:rsa\b|integers?)"),
    ("rsa-4096", r"\brsa[\s-]*4096\b|\b4096[\s-]*bit\s+(?:rsa\b|integers?)"),
    ("ecdlp-256", r"\bsecp256k1\b|\bsecp256r1\b|\bp-?256\b|\bcurve25519\b|\bed25519\b"
                  r"|\b256[\s-]*bit\s+(?:prime[\s-]*field\s+)?(?:elliptic|ecc|private key|curve)"),
    ("ecdlp-384", r"\bp-?384\b|\b384[\s-]*bit\s+(?:elliptic|ecc|curve)"),
    ("dlp-ffdhe-2048", r"\bffdhe2048\b|\b2048[\s-]*bit\s+(?:diffie|finite[\s-]field|dh\b)"),
    ("pairing-bls12-381", r"\bbls12-?381\b"),
    ("pairing-bn254", r"\bbn-?254\b|\balt-?bn128\b"),
]
_TARGETS_C = [(k, re.compile(p, re.I)) for k, p in _TARGETS]


def canonical_target(text: str):
    """Return the canonical target id for text, or None. Code decides, never the model."""
    t = norm(text)
    for key, rx in _TARGETS_C:
        if rx.search(t):
            return key
    return None


def all_targets(text: str) -> set:
    """Every canonical target mentioned in text."""
    t = norm(text)
    return {key for key, rx in _TARGETS_C if rx.search(t)}
