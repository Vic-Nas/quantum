"""Allowlisted fetchers. Each returns a list of item dicts with a stable id."""
import re
import urllib.parse
import xml.etree.ElementTree as ET

from . import http
from .textutil import norm

ALLOWLIST = ("arxiv.org", "eprint.iacr.org")

ARXIV_QUERIES = [
    'abs:"discrete logarithm" AND abs:quantum',
    'abs:"elliptic curve" AND abs:"logical qubits"',
    'abs:"elliptic curve" AND abs:quantum AND cat:quant-ph',
    'abs:RSA AND abs:"logical qubits"',
    'abs:Shor AND abs:"resource estimate"',
    'abs:factoring AND abs:"physical qubits"',
    'au:Gidney', 'au:Ekera', 'au:Litinski', 'au:Roetteler',
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
    for q in queries or ARXIV_QUERIES:
        params = urllib.parse.urlencode({"search_query": q, "start": 0, "max_results": max_results,
                                         "sortBy": "submittedDate", "sortOrder": "descending"})
        for it in parse_arxiv(http.get("https://export.arxiv.org/api/query?" + params)):
            if it["id"] not in seen:
                seen.add(it["id"])
                items.append(it)
    return items


def fetch_arxiv_ids(ids):
    """Fetch specific arXiv papers by id (used to build the baseline)."""
    q = urllib.parse.urlencode({"id_list": ",".join(ids), "max_results": len(ids)})
    return parse_arxiv(http.get("https://export.arxiv.org/api/query?" + q))


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
