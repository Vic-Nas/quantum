"""Model stages. Models only classify and quote; they never produce dates or headline data."""
from . import llm

COARSE_SCHEMA = {"type": "OBJECT", "properties": {
    "relevant": {"type": "BOOLEAN"}, "reason": {"type": "STRING"}}, "required": ["relevant", "reason"]}

EXTRACT_SCHEMA = {"type": "OBJECT", "properties": {
    "kind": {"type": "STRING", "enum": ["attack", "hardware", "none"]},
    "estimates": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
        "quote": {"type": "STRING"},
        "fields": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "name": {"type": "STRING"}, "value": {"type": "STRING"}},
            "required": ["name", "value"]}}},
        "required": ["quote", "fields"]}}}, "required": ["kind", "estimates"]}

COARSE_PROMPT = """You are a strict filter. Answer one closed question.
Does the text below give a NEW quantitative resource estimate for breaking a named cryptosystem
(RSA, elliptic curve, discrete log) with a quantum computer, OR a public hardware claim with
stated logical or physical qubit numbers? Surveys, post-quantum cipher design and pure theory
without numbers are NOT relevant. When unsure, answer true.

TITLE: {title}
TEXT: {text}"""

EXTRACT_PROMPT = """Extract this paper's OWN new results from the text. Rules:
- Use ONLY the text. Never use prior knowledge. Never compute or convert units.
- Skip numbers the authors cite from earlier work (for example 'previously 20 million qubits').
- Emit one estimate per (target, machine) result. Each estimate has:
  quote: ONE contiguous passage copied verbatim from the text (at most two sentences) that
         contains the target and every number you report for it.
  fields: name/value pairs, values copied as written.
- kind "attack" field names: target (the cryptosystem as named), logical_qubits, physical_qubits,
  toffoli_or_t_count, runtime (the duration phrase as written, for example '3.14 days').
- kind "hardware" field names: actor, logical_qubits, physical_qubits, target_year.
- Omit fields you cannot quote. If nothing applies, kind "none" with no estimates.

TITLE: {title}
TEXT: {text}"""


def coarse(item: dict, model: str) -> dict:
    return llm.generate(model, COARSE_PROMPT.format(title=item["title"], text=item["text"]), COARSE_SCHEMA)


def extract(item: dict, model: str) -> dict:
    out = llm.generate(model, EXTRACT_PROMPT.format(title=item["title"], text=item["text"]), EXTRACT_SCHEMA)
    ests = [{"quote": e.get("quote", ""), "fields": {f["name"]: f["value"] for f in e.get("fields", [])}}
            for e in out.get("estimates", [])]
    return {"kind": out.get("kind", "none"), "estimates": ests}
