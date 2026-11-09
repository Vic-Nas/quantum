"""Gemini free-tier client. Disk-cached, paced per model, with a daily request budget guard.

Free-tier limits (from the AI Studio rate-limit page, checked 2026-11-08):
  gemini-3.5-flash-lite / 3.1-flash-lite: 15 RPM, 250K TPM, 500 RPD
  gemma-4-26b / 31b:                      30 RPM,  16K TPM, 14.4K RPD
  gemini 3/3.6/3.8/2.5 flash:              5 RPM, 250K TPM,  20 RPD
Names get retired, so models are overridable by env and the name is stored in every audit record.
"""
import datetime as dt
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

CACHE = Path(os.environ.get("QTD_CACHE", "data/cache"))
# Roles with ordered fallback chains. Names get retired, so each role can fall through.
CHAINS = {
    "coarse": ["gemma-4-26b-a4b-it", "gemini-3.1-flash-lite"],
    "primary": ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"],
    # Chosen by comparison on the gold set (see evaluate.compare): Gemma confirmed 3 to 4 of 9, this one 8 of 9, with no errors.
    "secondary": ["gemini-3.1-flash-lite", "gemma-4-31b-it"],
    "escalation": ["gemini-3.8-flash", "gemini-3.6-flash"],
}
for _role in CHAINS:  # env override puts a model first in its chain
    _env = os.environ.get(f"QTD_MODEL_{_role.upper()}")
    if _env:
        CHAINS[_role] = [_env] + [m for m in CHAINS[_role] if m != _env]
MODELS = {role: chain[0] for role, chain in CHAINS.items()}


def family(model: str) -> str:
    return "gemma" if model.startswith("gemma") else "gemini"


def call_chain(role: str, fn, exclude: str | None = None):
    """Try each model in the role's chain (skipping `exclude`). fn(model) -> result. Returns (result, model_used)."""
    last = None
    for model in CHAINS[role]:
        if model == exclude:
            continue
        try:
            return fn(model), model
        except LLMError as e:
            last = e
    raise LLMError(f"all models failed for role {role}: {last}")


# model -> (min seconds between calls, requests per day). Interval covers both RPM and TPM.
LIMITS = {"gemini-3.5-flash-lite": (4.6, 500), "gemini-3.1-flash-lite": (4.6, 500),
          "gemma-4-26b-a4b-it": (5.0, 14400), "gemma-4-31b-it": (5.0, 14400)}
DEFAULT_LIMIT = (13.0, 20)  # 5 RPM / 20 RPD models
BUDGET_FRACTION = 0.8       # never spend more than this share of the daily quota
_last_call = {}
_run_budget = None  # a cap on real API requests in this process (None = no cap); the frequent retry runs set one
_run_calls = 0


def set_run_budget(n):
    """Cap the real API requests this process may make. Cache hits are free and not counted."""
    global _run_budget, _run_calls
    _run_budget, _run_calls = n, 0


class LLMError(RuntimeError):
    pass


def _today() -> str:
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=8)).strftime("%Y-%m-%d")  # Pacific reset


def _spend(model: str) -> None:
    """Count one request against today's budget or raise."""
    global _run_calls
    if _run_budget is not None and _run_calls >= _run_budget:
        raise LLMError(f"this run's cap of {_run_budget} API requests is used up")
    _run_calls += 1
    path = CACHE / "usage.json"
    usage = json.loads(path.read_text()) if path.exists() else {}
    day = usage.setdefault(_today(), {})
    cap = int(LIMITS.get(model, DEFAULT_LIMIT)[1] * BUDGET_FRACTION)
    if day.get(model, 0) >= cap:
        raise LLMError(f"daily budget reached for {model} ({cap} requests)")
    day[model] = day.get(model, 0) + 1
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({_today(): day}))


def parse_json(text: str):
    """Tolerant parse: models sometimes wrap JSON in code fences or add stray text."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise json.JSONDecodeError("no JSON object", text, 0)
    return json.loads(text[start:end + 1])


def generate(model: str, prompt: str, schema: dict, use_cache: bool = True) -> dict:
    """Return parsed JSON matching schema. Raises LLMError on failure."""
    key = hashlib.sha256(json.dumps([model, prompt, schema], sort_keys=True).encode()).hexdigest()
    path = CACHE / f"{key}.json"
    if use_cache and path.exists():
        return json.loads(path.read_text())
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise LLMError("GEMINI_API_KEY not set")
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json",
                             "responseSchema": schema},
    }).encode()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    interval = LIMITS.get(model, DEFAULT_LIMIT)[0]
    err = None
    for attempt in range(4):
        wait = interval - (time.time() - _last_call.get(model, 0.0))
        if wait > 0:
            time.sleep(wait)
        _spend(model)
        _last_call[model] = time.time()
        req = urllib.request.Request(url, data=body, headers={
            "Content-Type": "application/json", "x-goog-api-key": api_key})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.load(r)
            out = parse_json(data["candidates"][0]["content"]["parts"][0]["text"])
            CACHE.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(out))
            return out
        except urllib.error.HTTPError as e:
            err = f"HTTP {e.code}: {e.read()[:160]!r}"
            if e.code in (429, 500, 503):
                time.sleep(10 * (attempt + 1))
                continue
            break
        except (KeyError, IndexError, json.JSONDecodeError, OSError) as e:  # OSError covers timeouts and URLError
            err = repr(e)
            time.sleep(3)
    raise LLMError(f"{model}: {err or 'unknown'}")
