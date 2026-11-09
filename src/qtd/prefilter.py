"""Deterministic pre-filter. Tuned to over-include; a false positive costs one inbox line."""
import re

_ATTACK = re.compile(
    r"shor|discrete log|ecdlp|elliptic curve|\brsa\b|factor(?:ing|ization)|logical qubit|toffoli"
    r"|resource estimate|fault[\s-]tolerant|surface code|secp256|curve25519|ed25519|cryptanaly|\bt[\s-]count",
    re.I)
_QUANTUM = re.compile(r"quantum|qubit", re.I)
_HARDWARE = re.compile(
    r"logical qubit|below threshold|error[\s-]corrected|roadmap|fault[\s-]tolerant|physical qubit", re.I)


def prefilter(item: dict) -> dict:
    blob = f"{item.get('title','')} {item.get('text','')}"
    terms = sorted({m.group(0).lower() for m in _ATTACK.finditer(blob)})
    quantum = bool(_QUANTUM.search(blob))
    hw = bool(_HARDWARE.search(blob))
    keep = quantum and (len(terms) >= 2 or hw)
    return {"keep": keep, "terms": terms, "hardware_hint": hw}
