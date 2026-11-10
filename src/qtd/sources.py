"""Allowlisted fetchers. Each returns a list of item dicts with a stable id."""
import hashlib
import re
import time
import urllib.parse
from html.parser import HTMLParser
import xml.etree.ElementTree as ET

from . import http
from .textutil import norm

ALLOWLIST = ("arxiv.org", "eprint.iacr.org", "ionq.com", "quantinuum.com", "quantumai.google", "ibm.com",
             "signal.org", "openssh.org", "support.apple.com", "developers.cloudflare.com", "ethereum.org",
             "strongswan.org", "1password.com", "wireguard.com", "chaincode.com")

ARXIV_QUERIES = [
    'abs:"discrete logarithm" AND abs:quantum',
    'abs:"elliptic curve" AND abs:"logical qubits"',
    'abs:"elliptic curve" AND abs:quantum AND (abs:Toffoli OR abs:qubits)',
    'abs:RSA AND abs:"logical qubits"',
    'abs:RSA AND abs:factoring AND abs:qubits',
    'abs:Shor AND abs:"resource estimate"',
    'abs:factoring AND abs:"physical qubits"',
    'abs:Grover AND (abs:AES OR abs:SHA)',
    'abs:secp256k1 AND abs:quantum',
    'au:Gidney', 'au:Ekera', 'au:Litinski', 'au:Roetteler', 'au:Schrottenloher', 'au:Gouzien', 'au:Babbush',
]
_NS = {"a": "http://www.w3.org/2005/Atom"}


def is_allowlisted(url: str) -> bool:
    host = urllib.parse.urlparse(url).hostname or ""
    return any(host == d or host.endswith("." + d) for d in ALLOWLIST)


def parse_arxiv(xml_bytes: bytes):
    items = []
    for e in ET.fromstring(xml_bytes).findall("a:entry", _NS):
        url = e.findtext("a:id", "", _NS)
        m = re.search(r"arxiv\.org/abs/(.+?)(v\d+)?$", url)
        if not m:
            continue
        items.append({
            "id": f"arxiv:{m.group(1)}",
            "version": (m.group(2) or "v1")[1:],
            "source": "arxiv",
            "url": url,
            "title": norm(e.findtext("a:title", "", _NS)),
            "text": norm(e.findtext("a:summary", "", _NS)),
            "published": e.findtext("a:published", "", _NS)[:10],
            "updated": e.findtext("a:updated", "", _NS)[:10],
        })
    return items


def fetch_arxiv(max_results: int = 50, queries=None):
    seen, items = set(), []
    for n, q in enumerate(queries or ARXIV_QUERIES):
        if n:
            time.sleep(http.ARXIV_MIN_INTERVAL)
        params = urllib.parse.urlencode({"search_query": q, "start": 0, "max_results": max_results,
                                         "sortBy": "submittedDate", "sortOrder": "descending"})
        for it in parse_arxiv(http.get("https://export.arxiv.org/api/query?" + params)):
            if it["id"] not in seen:
                seen.add(it["id"])
                items.append(it)
    return items


def fetch_arxiv_ids(ids):
    """Fetch specific arXiv papers by id (used to build the baseline)."""
    items = []
    for k in range(0, len(ids), 4):  # small batches: arXiv is slow and rate limited
        batch = ids[k:k + 4]
        q = urllib.parse.urlencode({"id_list": ",".join(batch), "max_results": len(batch)})
        items += parse_arxiv(http.get("https://export.arxiv.org/api/query?" + q, timeout=90))
    return items


def backfill(ids):
    """Fetch older papers by id for the history timeline. They are marked so the router accepts them as history."""
    items = fetch_arxiv_ids(ids)
    for it in items:
        it["version"], it["history"] = "seed", True
    return items


def parse_eprint(xml_bytes: bytes):
    items = []
    root = ET.fromstring(xml_bytes)
    for e in root.iter("item"):
        url = e.findtext("link", "")
        m = re.search(r"/(\d{4}/\d+)", url)
        if not m:
            continue
        items.append({
            "id": f"eprint:{m.group(1)}", "version": "1", "source": "eprint", "url": url,
            "title": norm(e.findtext("title", "")),
            "text": norm(re.sub(r"<[^>]+>", " ", e.findtext("description", ""))),
            "published": "", "updated": "",
        })
    return items


def fetch_eprint():
    return parse_eprint(http.get("https://eprint.iacr.org/rss/rss.xml"))


class _Text(HTMLParser):
    """Visible text of a page: skips scripts, styles and hidden chrome, keeps block boundaries as newlines."""
    SKIP = {"script", "style", "noscript", "svg", "head", "template"}
    BLOCK = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "br", "section", "article", "td", "th", "blockquote"}

    def __init__(self):
        super().__init__()
        self.parts, self.skip, self.title, self._in_title = [], 0, "", False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        if tag in self.SKIP and tag != "head":
            self.skip += 1
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag in self.SKIP and tag != "head":
            self.skip = max(0, self.skip - 1)
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self.skip:
            self.parts.append(data)


def html_to_text(raw: str):
    """Return (title, text) with one block of text per line and runs of whitespace collapsed."""
    p = _Text()
    p.feed(raw)
    lines = [re.sub(r"[ \t\u00a0]+", " ", ln).strip() for ln in "".join(p.parts).split("\n")]
    return norm(p.title), "\n".join(ln for ln in lines if ln)


def pdf_to_text(pdf: bytes) -> str:
    """Text of a PDF. Prefers pdftotext with layout (keeps table rows on one line), falls back to pypdf."""
    import shutil
    import subprocess
    if shutil.which("pdftotext"):
        r = subprocess.run(["pdftotext", "-layout", "-", "-"], input=pdf, capture_output=True, timeout=120)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.decode("utf-8", "replace")
    try:
        import io
        from pypdf import PdfReader
        return "\n".join((pg.extract_text() or "") for pg in PdfReader(io.BytesIO(pdf)).pages)
    except Exception:  # noqa: BLE001
        return ""


def fetch_fulltext(arxiv_id: str):
    """Full text of an arXiv paper ('arxiv:2609.05625' or '2609.05625'), as one string with one text line per line, or ''."""
    num = arxiv_id.split(":", 1)[-1]
    try:
        raw = pdf_to_text(http.get(f"https://arxiv.org/pdf/{num}", timeout=90))
    except RuntimeError:
        return ""
    lines = [re.sub(r"[ \t\u00a0]+", " ", ln).strip() for ln in raw.replace("\f", "\n").split("\n")]
    return "\n".join(ln for ln in lines if ln)


def fetch_pages(sources):
    """Fetch configured vendor pages. sources: [{'url', 'actor'}]. Returns items shaped like paper items."""
    items = []
    for s in sources:
        if not is_allowlisted(s["url"]):
            continue
        raw = http.get(s["url"]).decode("utf-8", "replace")
        title, text = html_to_text(raw)
        items.append({"id": "page:" + urllib.parse.urlparse(s["url"]).netloc + urllib.parse.urlparse(s["url"]).path.rstrip("/"),
                      "version": hashlib.sha256(text.encode()).hexdigest()[:12], "source": "page", "url": s["url"],
                      "actor": s["actor"], "title": title or s["actor"], "text": text, "published": "", "updated": ""})
    return items


def fetch_all():
    items, errors = [], {}
    for name, fn in (("arxiv", fetch_arxiv), ("eprint", fetch_eprint)):
        try:
            got = fn()
            items += got
            if not got:
                errors[name] = "zero items (source health alert)"
        except Exception as e:  # noqa: BLE001
            errors[name] = str(e)
    return items, errors
