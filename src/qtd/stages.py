"""Model stages. Models only classify and quote; they never produce dates or headline data."""
from . import llm
from .present import strip_dashes

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
    out = llm.generate(model, COARSE_PROMPT.format(title=item["title"], text=item["text"]), COARSE_SCHEMA)
    if isinstance(out.get("reason"), str):  # free text written by a model: keep dashes out of it
        out["reason"] = strip_dashes(out["reason"])
    return out


def source_text(item: dict) -> str:
    """The exact text the model reads and the verifier checks quotes against. The title is included
    because some papers state their result only in the title."""
    return f"{item['title']}. {item['text']}"


def extract_prompt(item: dict) -> str:
    return EXTRACT_PROMPT.format(title=item["title"], text=source_text(item))


def extract(item: dict, model: str) -> dict:
    out = llm.generate(model, extract_prompt(item), EXTRACT_SCHEMA)
    ests = [{"quote": e.get("quote", ""), "fields": {f["name"]: f["value"] for f in e.get("fields", [])}}
            for e in out.get("estimates", [])]
    return {"kind": out.get("kind", "none"), "estimates": ests}


HARDWARE_PROMPT = """Extract quantum computer hardware plans and claims from the text. Rules:
- Use ONLY the text. Never use prior knowledge. Never compute or convert.
- Only the company's own systems or plans. Ignore other companies and results cited as background.
- Emit one estimate per claim that states BOTH a qubit count AND a year. Omit anything missing either.
- Each estimate has:
  quote: ONE contiguous passage copied verbatim from the text (at most two sentences) that contains the year and the numbers.
  fields: name/value pairs copied as written: physical_qubits, logical_qubits, target_year (for example 2029).
- Use kind "hardware". If nothing qualifies, kind "none" with no estimates.

TITLE: {title}
TEXT: {text}"""


def hardware_prompt(item: dict) -> str:
    return HARDWARE_PROMPT.format(title=item["title"], text=item["text"])


def extract_hardware(item: dict, model: str) -> dict:
    out = llm.generate(model, hardware_prompt(item), EXTRACT_SCHEMA)
    ests = [{"quote": e.get("quote", ""), "fields": {f["name"]: f["value"] for f in e.get("fields", [])}}
            for e in out.get("estimates", [])]
    return {"kind": out.get("kind", "none"), "estimates": ests}


def chunks(text: str, size: int = 12000):
    """Split page text into pieces of at most `size` characters on line boundaries."""
    out, cur = [], ""
    for line in text.split("\n"):
        if cur and len(cur) + len(line) + 1 > size:
            out.append(cur)
            cur = ""
        cur += line + "\n"
    if cur.strip():
        out.append(cur)
    return out
