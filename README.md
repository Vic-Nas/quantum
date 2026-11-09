<!-- site:start -->
<h1><a href="https://quantum.vicnas.me/"><img src="web/favicon.svg" alt="" width="30" height="30" align="absmiddle"> Quantum threat tracker</a></h1>
<!-- site:end -->

Published estimates of how many qubits it takes to break today's encryption, with each paper as proof.
Models propose, code verifies.

```bash
export GEMINI_API_KEY=...
PYTHONPATH=src python3 -m qtd run      # fetch, extract, verify, apply
PYTHONPATH=src python3 -m qtd hardware # read vendor roadmap pages (also part of run)
PYTHONPATH=src python3 -m qtd retry    # self-healing pass (queued papers, vendor pages, full pass if the last run failed)
PYTHONPATH=src python3 -m qtd eval     # score regex and models against data/gold/gold.jsonl
PYTHONPATH=src python3 -m qtd.site site
python3 -m unittest discover -s tests
```

GitHub Actions runs the full pipeline daily, runs a cheap self-healing pass every 2 hours, and republishes the page
when design files change. It needs the secret `GEMINI_API_KEY`, the variable `QTD_SITE_URL` (the page address,
also used for the title link above) and Settings > Pages > Source set to "GitHub Actions".
