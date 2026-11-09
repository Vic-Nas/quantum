"""Deterministic baseline extractor. Same output shape as the model extractor."""
import re

from .textutil import all_targets, norm

_N = (r"((?:\d{1,3}(?:[,   ]\d{3})+|\d+)(?:\.\d+)?(?:\s*(?:thousand|million|billion)|k\b)?"
      r"|(?:a|one)\s+(?:thousand|million|billion))")
_PATTERNS = {
    "logical_qubits": re.compile(_N + r"\s+(?:error[\s-]corrected\s+)?logical\s+qubits", re.I),
    "physical_qubits": re.compile(_N + r"\s+(?:(?:noisy|physical|superconducting)\s+)+qubits", re.I),
    "toffoli_or_t_count": re.compile(_N + r"\s+toffoli", re.I),
    "runtime": re.compile(r"((?:\d+(?:\.\d+)?|a|an|one|two|three|four|five|six|seven|eight|nine|ten)"
                          r"\s*[- ]?(?:minute|hour|day|week|month)s?)", re.I),
}


def _sentences(text: str):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", norm(text)) if s.strip()]


def extract(text: str, kind: str = "attack"):
    """One estimate per sentence naming a target (plus the next sentence if it names none)."""
    sents = _sentences(text)
    ests = []
    for i, sent in enumerate(sents):
        tg = sorted(all_targets(sent))
        if not tg:
            continue
        quote = sent
        if i + 1 < len(sents) and not all_targets(sents[i + 1]):
            quote = f"{sent} {sents[i + 1]}"
        fields = {"target": tg[0]}
        for name, rx in _PATTERNS.items():
            m = rx.search(quote)
            if m:
                fields[name] = m.group(1).strip()
        if len(fields) > 1:
            ests.append({"quote": quote, "fields": fields})
    return {"kind": kind if ests else "none", "estimates": ests}
