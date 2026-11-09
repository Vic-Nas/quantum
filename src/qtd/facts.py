"""Facts that sources can supply: post-quantum status of services, funds exposed to a quantum attack.

Each configured page is re-read when it changes. Two models answer one closed question about it, code checks that the
quote is verbatim in the page and that the answer is in the quote, and both models must agree. Entries marked
"manual": true in data/facts.json are a person's call and are never touched.
"""
import datetime as dt
import hashlib
import json
from pathlib import Path

from . import http, llm, sources
from .present import SERVICES
from .stages import chunks
from .textutil import norm

DATA = Path("data")
STATUSES = ("protected", "migrating", "partial", "none")
MAX_QUOTE = 400

SCHEMA = {"type": "OBJECT", "properties": {"answer": {"type": "STRING"}, "quote": {"type": "STRING"}},
          "required": ["answer", "quote"]}

PQ_PROMPT = """Question: what is the post-quantum cryptography status of {topic} ({what})?
Answer with exactly one word:
protected: post-quantum protection is on by default for users
migrating: shipping but opt-in, or announced with a plan
partial: only some parts are protected
none: the text says there is no post-quantum protection
unknown: the text does not say
Use ONLY the text. quote: ONE contiguous passage copied verbatim from the text (at most two sentences) that supports
your answer. Empty if unknown.

TITLE: {title}
TEXT: {text}"""

FIGURE_PROMPT = """Question: {ask}
answer: the figure exactly as written in the text, with its unit (for example '1.7 million BTC'), or 'unknown'.
Use ONLY the text. Never compute or convert. quote: ONE contiguous passage copied verbatim from the text (at most two
sentences) that contains that figure. Empty if unknown.

TITLE: {title}
TEXT: {text}"""


def _load(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def _flat(s: str) -> str:
    return norm(s).lower().replace(",", "").replace(" ", "")


def prompt(src: dict, title: str, text: str) -> str:
    if src["kind"] == "pq":
        return PQ_PROMPT.format(topic=src["topic"], what=src["what"], title=title, text=text)
    return FIGURE_PROMPT.format(ask=src["ask"], title=title, text=text)


def check(src: dict, out: dict, page: str):
    """Return the verified answer string, or None. Code, not the model, decides whether the quote supports it."""
    ans, quote = norm(str(out.get("answer", ""))).strip(), norm(str(out.get("quote", ""))).strip()
    if not ans or ans.lower() == "unknown" or not quote or len(quote) > MAX_QUOTE or quote.lower() not in page:
        return None
    if src["kind"] == "pq":
        ans = ans.lower()
        return ans if ans in STATUSES else None
    return ans if _flat(ans) in _flat(quote) else None


def _same(a: str, b: str) -> bool:
    return _flat(a) == _flat(b)


def _page(url: str):
    raw = http.get(url, timeout=90)
    if url.lower().split("?")[0].endswith(".pdf"):
        return "", sources.pdf_to_text(raw)
    return sources.html_to_text(raw.decode("utf-8", "replace"))


def run(dry: bool = False, only: list | None = None) -> dict:
    srcs = only if only is not None else _load(DATA / "facts_sources.json", [])
    facts = _load(DATA / "facts.json", {})
    seen = _load(DATA / "facts_seen.json", {})
    summary = {"sources": len(srcs), "changed": 0, "applied": 0, "unconfirmed": 0, "unavailable": 0, "errors": {}}
    pages = {}
    for s in srcs:
        if facts.get(s["id"], {}).get("manual"):
            continue
        if not sources.is_allowlisted(s["url"]):
            summary["errors"][s["id"]] = "host not on the allowlist"
            continue
        if s["url"] not in pages:
            try:
                title, text = _page(s["url"])
                pages[s["url"]] = (title, text, hashlib.sha256(text.encode()).hexdigest()[:12])
            except RuntimeError as e:
                pages[s["url"]] = None
                summary["errors"][s["id"]] = str(e)[:120]
        got = pages[s["url"]]
        if got is None:
            continue
        title, text, version = got
        if seen.get(s["id"]) == version:
            continue
        summary["changed"] += 1
        page = norm(text).lower()
        found, complete = None, True
        for chunk in chunks(text):
            try:
                o1, m1 = llm.call_chain("primary", lambda m: llm.generate(m, prompt(s, title, chunk), SCHEMA))
                a1 = check(s, o1, page)
                if a1 is None:
                    continue
                o2, m2 = llm.call_chain("secondary", lambda m: llm.generate(m, prompt(s, title, chunk), SCHEMA), exclude=m1)
            except llm.LLMError:
                complete = False
                break
            a2 = check(s, o2, page)
            if a2 is not None and _same(a1, a2):
                found = {"answer": a1, "quote": norm(o1["quote"]).strip(), "models": {"primary": m1, "secondary": m2}}
                break
        if not complete:
            summary["unavailable"] += 1  # left unseen so the next run tries again
            continue
        seen[s["id"]] = version
        if found is None:
            summary["unconfirmed"] += 1
            continue
        entry = {**{k: s[k] for k in ("kind", "topic", "group", "label") if k in s}, **found, "url": s["url"],
                 "checked": dt.date.today().isoformat()}
        if {k: entry.get(k) for k in ("answer", "quote")} != {k: facts.get(s["id"], {}).get(k) for k in ("answer", "quote")}:
            summary["applied"] += 1
        facts[s["id"]] = entry
    # Services nothing can read: a person adds one line to data/facts.json with "manual": true.
    covered = {s["topic"] for s in _load(DATA / "facts_sources.json", []) if s["kind"] == "pq"}
    summary["needs_a_person"] = sorted(n for n, *_ in SERVICES if n not in covered and not facts.get(n, {}).get("manual"))
    if not dry:
        (DATA / "facts.json").write_text(json.dumps(facts, indent=1) + "\n")
        (DATA / "facts_seen.json").write_text(json.dumps(seen, indent=1) + "\n")
    return summary
