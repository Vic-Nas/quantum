import argparse
import json

from . import evaluate, facts, pipeline, pq_releases

ap = argparse.ArgumentParser(prog="qtd")
sub = ap.add_subparsers(dest="cmd", required=True)
r = sub.add_parser("run", help="fetch, filter, extract, verify, route")
r.add_argument("--no-llm", action="store_true", help="dry run: writes nothing")
r.add_argument("--no-auto", action="store_true", help="hold every Tier A row instead of applying")
r.add_argument("--limit", type=int)
sub.add_parser("hardware", help="fetch vendor roadmap pages and extract hardware claims")
sub.add_parser("retry", help="self-healing pass: queued papers, vendor pages, and a full pass if the last run failed")
sub.add_parser("seed", help="one-time baseline from the gold papers")
sub.add_parser("facts", help="re-read fact sources (service PQ status, exposed funds) and store what two models confirm")
sub.add_parser("pq", help="check GitHub releases of tracked projects for post-quantum keywords")
e = sub.add_parser("eval", help="score regex and models against the gold set")
e.add_argument("--no-llm", action="store_true")
a = ap.parse_args()
if a.cmd == "run":
    out = {"papers": pipeline.run(use_llm=not a.no_llm, limit=a.limit, auto_apply=not a.no_auto, fulltext=True)}
    if not a.no_llm:
        out["hardware"] = pipeline.run_hardware()
    print(json.dumps(out, indent=1))
elif a.cmd == "hardware":
    print(json.dumps(pipeline.run_hardware(), indent=1))
elif a.cmd == "retry":
    print(json.dumps(pipeline.retry(), indent=1))
elif a.cmd == "seed":
    print(json.dumps(pipeline.seed(), indent=1))
elif a.cmd == "facts":
    print(json.dumps(facts.run(), indent=1))
elif a.cmd == "pq":
    print(json.dumps(pq_releases.run(), indent=1))
else:
    print(json.dumps(evaluate.run(use_llm=not a.no_llm), indent=1))
