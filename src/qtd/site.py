"""Build the static site folder: a JSON data feed plus a plain table (real page comes later)."""
import html
import json
import shutil
import sys
from pathlib import Path


def build(out="site"):
    out = Path(out)
    shutil.rmtree(out, ignore_errors=True)
    (out / "data").mkdir(parents=True)
    for f in ("attacks.json", "hardware.json", "status.json", "queue.json"):
        src = Path("data") / f
        (out / "data" / f).write_text(src.read_text() if src.exists() else "[]")
    rows = json.loads((out / "data" / "attacks.json").read_text())
    status = json.loads((out / "data" / "status.json").read_text() or "{}") if (Path("data") / "status.json").exists() else {}
    tr = "".join(
        f"<tr><td>{html.escape(str(r.get('target')))}</td><td>{r.get('logical_qubits', '')}</td>"
        f"<td>{r.get('physical_qubits', '')}</td><td>{r.get('runtime', '')}</td>"
        f"<td><a href='{html.escape(r['url'])}'>{html.escape(r['title'][:70])}</a></td>"
        f"<td>{html.escape(r['quote'])}</td></tr>" for r in sorted(rows, key=lambda r: str(r.get("target"))))
    (out / "index.html").write_text(
        "<!doctype html><meta charset=utf-8><title>Quantum threat data</title>"
        "<h1>Quantum threat data (raw feed)</h1><p>Last run: "
        f"{html.escape(str(status.get('run_at', 'never')))}. Data: <a href='data/attacks.json'>attacks.json</a></p>"
        "<table border=1 cellpadding=4><tr><th>target</th><th>logical qubits</th><th>physical qubits</th>"
        f"<th>runtime (h)</th><th>source</th><th>verbatim quote</th></tr>{tr}</table>")
    return out


if __name__ == "__main__":
    print(build(*sys.argv[1:]))
