import argparse
import json

from . import evaluate, pipeline

ap = argparse.ArgumentParser(prog="qtd")
sub = ap.add_subparsers(dest="cmd", required=True)
r = sub.add_parser("run", help="fetch, filter, extract, verify, route")
r.add_argument("--no-llm", action="store_true")
r.add_argument("--limit", type=int)
e = sub.add_parser("eval", help="score regex and models against the gold set")
e.add_argument("--no-llm", action="store_true")
a = ap.parse_args()
if a.cmd == "run":
    print(json.dumps(pipeline.run(use_llm=not a.no_llm, limit=a.limit), indent=1))
else:
    print(json.dumps(evaluate.run(use_llm=not a.no_llm), indent=1))
