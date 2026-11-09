# quantum

Pipeline for a quantum threat dashboard (no web page yet). It ingests public sources, extracts
resource estimates with free-tier models, and verifies everything in plain code.

Rules: models only propose, code verifies, and nothing a model produced can change a date
without a human merge (Tier A). Everything else goes to the radar (Tier B) and never affects dates.

## Run

```bash
export GEMINI_API_KEY=...        # free tier is enough
PYTHONPATH=src python3 -m qtd run --no-llm   # fetch, prefilter, regex only
PYTHONPATH=src python3 -m qtd run            # full pipeline
PYTHONPATH=src python3 -m qtd eval           # score regex and models against data/gold/gold.jsonl
python3 -m unittest discover -s tests
```

Model roles and free-tier limits are in `src/qtd/llm.py`. Names are overridable with
`QTD_MODEL_COARSE`, `QTD_MODEL_PRIMARY`, `QTD_MODEL_SECONDARY`.

The gold set in `data/gold/gold.jsonl` was labeled by reading abstracts and needs human spot-checks.
