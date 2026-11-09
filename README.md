# quantum

Pipeline and page tracking published quantum attack estimates. Models propose, code verifies.

```bash
export GEMINI_API_KEY=...
PYTHONPATH=src python3 -m qtd run      # fetch, extract, verify, apply (--no-llm for a dry run)
PYTHONPATH=src python3 -m qtd eval     # score regex and models against data/gold/gold.jsonl
PYTHONPATH=src python3 -m qtd.site site
python3 -m unittest discover -s tests
```

`.github/workflows/daily.yml` runs twice a day and on demand, then publishes to GitHub Pages.
It needs the secret `GEMINI_API_KEY`, the variable `QTD_SITE_URL` (the public page address),
and Settings > Pages > Source set to "GitHub Actions".
