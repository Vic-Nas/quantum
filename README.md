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

## Automation (GitHub Actions + Pages)

`.github/workflows/daily.yml` runs twice a day (the second pass retries items queued while the models
were down) and on demand from the Actions tab (`run`, `seed`, `eval`; options: dry run, hold all).
It needs the repo secret `GEMINI_API_KEY` and Settings > Pages > Source set to "GitHub Actions".

Policy: Tier A rows (a cheaper attack or a new hardware claim) are applied automatically when the
verifier passes and two model families agree. Automatic brakes: a canary that re-checks known papers
without the cache each run, and a cap of 3 new headline rows per run (more are held in `data/proposals`).
Model failures go to `data/queue.json` and are retried, then given up on after 6 attempts.
Every change is one commit, so a bad row is a one-line revert.
