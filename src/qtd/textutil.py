"""Plain-code helpers: number, duration and target parsing. No models involved."""
import re

_MULT = {"thousand": 1e3, "k": 1e3, "million": 1e6, "billion": 1e9, "trillion": 1e12}
_WORDNUM = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
            "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}

NUM_RE = re.compile(
    r"(?P<num>\d{1,3}(?:,\s?\d{3}|[\u202f\u00a0 ]\d{3})+(?!\d)(?:\.\d+)?|\d+(?:\.\d+)?|\ba\b|\ban\b|\bone\b|\btwo\b"
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
        raw = re.sub(r"[,\s\u202f\u00a0]", "", m.group("num").lower())
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
    ("dlp-ff-512", r"\bFFDLP[\s-]*512\b|\b512[\s-]*bit[\s-]+(?:finite[\s-]field|FFDLP)"),
    ("dlp-ffdhe-2048", r"\bffdhe2048\b|\b2048[\s-]*bit\s+(?:diffie|finite[\s-]field|dh\b)"),
    ("aes-128", r"\baes[\s-]*128\b"),
    ("aes-256", r"\baes[\s-]*256\b"),
    ("sha-256", r"\bsha[\s-]*(?:2[\s-]*)?256\b"),
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


def number_followed_by(text: str, value: float, word: str, window: int = 28) -> bool:
    """True if some occurrence of `value` in text is followed within `window` characters by `word` (case-insensitive)."""
    for m in NUM_RE.finditer(text or ""):
        raw = re.sub(r"[,\s\u202f\u00a0]", "", m.group("num").lower())
        try:
            v = float(raw)
        except ValueError:
            continue
        if m.group("mult"):
            v *= _MULT[m.group("mult").lower()]
        elif m.group("k"):
            v *= 1e3
        if abs(v - value) <= 1e-9 * max(1.0, abs(value)) and re.search(word, text[m.end(): m.end() + window], re.I):
            return True
    return False


def bits_row_for(target: str, quote: str, context: str = "") -> bool:
    """A table row such as '384 3484 4.52 x 10^11 ...' names its algorithm only by a size. True if `target` is
    'ecdlp-<bits>' or 'aes-<bits>' and that size stands alone as a number in the quote. For AES the paper's
    title (`context`) must also name AES, because the row itself never does."""
    m = re.fullmatch(r"(ecdlp|aes)-(\d+)", target or "")
    if not m:
        return False
    standalone = re.search(r"(?<![\d.,^])" + m.group(2) + r"(?![\d,.]|\s*-?\s*bit)", quote or "")
    if m.group(1) == "aes":
        return bool(standalone) and bool(re.search(r"\bAES\b", context or ""))
    return bool(standalone)


def qubit_regime(text: str):
    """'logical' if a paper only ever counts logical qubits (so an unlabeled '#qubits' column is logical), else None."""
    lg = len(re.findall(r"logical[\s-]+qubit", text or "", re.I))
    ph = len(re.findall(r"(?:physical|noisy|cat)[\s-]+qubit", text or "", re.I))
    return "logical" if lg >= 2 and ph == 0 else None


TARGET_IDS = {key for key, _ in _TARGETS}


def repair_quote(quote: str, src_lower: str, needles=()) -> str:
    """If a model joined passages with an ellipsis, keep the segment that appears verbatim in the source and
    contains the most of the `needles` (the claimed target and numbers); longer wins a tie."""
    segs = [norm(x) for x in re.split(r"\s*(?:\.\.\.|\u2026)\s*", quote or "") if x.strip()]
    ok = [x for x in segs if x.lower() in src_lower]
    if not ok:
        return quote
    hits = lambda seg: sum(1 for n in needles if str(n).strip() and str(n).strip().lower() in seg.lower())
    return max(ok, key=lambda seg: (hits(seg), len(seg)))


def infer_table_target(quote: str, context: str):
    """A table row without a label ('384 3484 4.52 x 10^11 ...') inside a paper about elliptic curves or AES.
    Returns 'ecdlp-<bits>' or 'aes-<bits>' when exactly one known size stands alone in the row, else None."""
    def standalone(n):
        return re.search(r"(?<![\d.,^])" + str(n) + r"(?![\d,.]|\s*-?\s*bit)", quote or "") is not None
    if re.search(r"elliptic|ECDLP", context or "", re.I):
        hits = [n for n in (256, 384) if standalone(n)]
        return f"ecdlp-{hits[0]}" if len(hits) == 1 else None
    if re.search(r"\bAES\b", context or ""):
        hits = [n for n in (128, 192, 256) if standalone(n)]
        return f"aes-{hits[0]}" if len(hits) == 1 else None
    return None


_MON = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
_MON_RE = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"


def _month_num(word: str):
    return _MON.get(word.strip(". ").lower()[:3])


def month_in_quote(raw: str, year, quote: str):
    """The month number (1 to 12) if `raw` names a month that the quote puts right next to `year`, else None.

    'June 2028', 'June 15, 2028' and '15 June 2028' count. A bare 'may' elsewhere in the sentence does not.
    """
    m = re.match(rf"^\W*({_MON_RE})\b", str(raw or "").strip(), re.I)
    if not m or year is None:
        return None
    want = _month_num(m.group(1))
    day = r"\d{1,2}(?:st|nd|rd|th)?"
    for pat in (rf"\b({_MON_RE})\.?\s+(?:{day},?\s+)?{int(year)}\b", rf"\b{day}\s+(?:of\s+)?({_MON_RE})\.?,?\s+{int(year)}\b"):
        for hit in re.finditer(pat, quote or "", re.I):
            if _month_num(hit.group(1)) == want:
                return want
    return None
