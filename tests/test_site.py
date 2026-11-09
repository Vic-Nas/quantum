import json
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from qtd import cards, present, site  # noqa: E402

ROWS = [
    {"id": "arxiv:1905.09749#0", "kind": "attack", "target": "rsa-2048", "physical_qubits": 20000000.0, "runtime": 8.0,
     "quote": "q0", "url": "https://arxiv.org/abs/1905.09749", "title": "RSA 2019", "published": "2019-05-23"},
    {"id": "arxiv:2505.15917#0", "kind": "attack", "target": "rsa-2048", "physical_qubits": 1000000.0, "runtime": 168,
     "quote": "q1", "url": "https://arxiv.org/abs/2505.15917", "title": "RSA 2025", "published": "2025-05-21"},
    {"id": "arxiv:2610.37839#3", "kind": "attack", "target": "rsa-2048", "physical_qubits": 45000.0,
     "quote": "q2", "url": "https://arxiv.org/abs/2610.37839", "title": "RSA 2026", "published": "2026-10-27"},
    {"id": "arxiv:2609.05625#4", "kind": "attack", "target": "ecdlp-256", "physical_qubits": 19397.0, "runtime": 616.8,
     "quote": "q3", "url": "https://arxiv.org/abs/2609.05625", "title": "ECDLP paper", "published": "2026-09-08"},
    {"id": "arxiv:2607.13816#7", "kind": "attack", "target": "ecdlp-256", "logical_qubits": 835.0,
     "quote": "q4", "url": "https://arxiv.org/abs/2607.13816", "title": "Logical paper", "published": "2026-07-15"},
]


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta, self.title, self._t = {}, "", False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta":
            self.meta[a.get("property") or a.get("name")] = a.get("content")
        self._t = tag == "title"

    def handle_data(self, d):
        if self._t:
            self.title += d

    def handle_endtag(self, tag):
        self._t = False


class Present(unittest.TestCase):
    def test_numbers_and_dates(self):
        self.assertEqual(present.short_count(20000000), "20 million")
        self.assertEqual(present.short_count(1500000), "1.5 million")
        self.assertEqual(present.short_count(45000), "45,000")
        self.assertEqual(present.date_label("2026-10-27"), "27 Oct 2026")
        self.assertEqual(present.date_label("2026-10-27", True), "Oct 2026")
        self.assertEqual(present.date_label(""), "")
        self.assertEqual(present.duration(168), "7 days")
        self.assertEqual(present.duration(1.25), "1.25 hours")

    def test_series_marks_records_and_skips_logical_only(self):
        pts = present.series(ROWS, "rsa-2048")
        self.assertEqual([p["y"] for p in pts], [20000000.0, 1000000.0, 45000.0])
        self.assertTrue(all(p["record"] for p in pts))
        self.assertEqual(len(present.series(ROWS, "ecdlp-256")), 1)  # logical-only row is not plotted
        worse = ROWS + [dict(ROWS[0], id="x#1", physical_qubits=5e6, published="2026-01-01")]
        flags = {p["row"]["id"]: p["record"] for p in present.series(worse, "rsa-2048")}
        self.assertFalse(flags["x#1"])

    def test_headline(self):
        h = present.headline(ROWS, "rsa-2048")
        self.assertEqual((h["first"]["y"], h["best"]["y"]), (20000000.0, 45000.0))
        self.assertAlmostEqual(h["drop_pct"], 99.8, places=1)
        self.assertIsNone(present.headline(ROWS, "rsa-4096"))

    def test_clean_and_ids(self):
        self.assertEqual(present.paper_id("arxiv:2609.05625#4"), "arXiv 2609.05625")
        self.assertEqual(present.dom_id("arxiv:2609.05625#4"), "p-arxiv-2609-05625-4")
        self.assertNotIn("\n", present.clean("a\nb\x00c"))
        self.assertLessEqual(len(present.clean("x" * 400, 20)), 20)


class Chart(unittest.TestCase):
    def test_svg_has_a_link_per_dot_and_valid_numbers(self):
        from qtd import chart
        pts = present.series(ROWS, "rsa-2048")
        svg = chart.timeline_svg(pts, 640, 330, "label")
        self.assertEqual(svg.count('class="dot'), 3)
        self.assertIn('href="#p-arxiv-2505-15917-0"', svg)
        self.assertNotIn("nan", svg.lower())
        self.assertEqual(chart.timeline_svg([], 640, 330, "x"), "")
        one = chart.timeline_svg(present.series(ROWS, "ecdlp-256"), 340, 300, "x")  # single point must not crash
        self.assertIn("<svg", one)


class Cards(unittest.TestCase):
    def test_home_card(self):
        c = cards.home_card(ROWS, "2026-11-09", "https://example.com/q/")
        self.assertIn("RSA-2048 needed 20 million qubits in 2019 and now 45,000", c["description"])
        self.assertIn("as of 2026-11-09", c["description"])
        self.assertTrue(c["url"].startswith("https://"))
        self.assertLessEqual(len(c["description"]), 250)
        self.assertLessEqual(len(c["title"]), 60)
        self.assertNotRegex(c["description"].lower(), r"\bago\b|just now")

    def test_empty_and_hostile(self):
        self.assertIn("No estimates", cards.home_card([], "", "https://e.com/")["description"])
        c = cards.home_card(ROWS, "2026\n<script>alert(1)</script>", "https://e.com/")
        self.assertNotIn("\n", c["description"])


class BaseUrl(unittest.TestCase):
    def test_env_empty_and_slash(self):
        import os
        from unittest import mock
        with mock.patch.dict(os.environ, {"QTD_SITE_URL": ""}):
            self.assertEqual(site.base_url(), site.DEFAULT_URL)
        with mock.patch.dict(os.environ, {"QTD_SITE_URL": "https://x.example/app"}):
            self.assertEqual(site.base_url(), "https://x.example/app/")


class Build(unittest.TestCase):
    def build(self, rows, status=None, cands=None):
        d, out = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp()) / "site"
        (d / "attacks.json").write_text(json.dumps(rows))
        if status is not None:
            (d / "status.json").write_text(json.dumps(status))
        if cands:
            (d / "candidates").mkdir()
            (d / "candidates" / "2026-11.jsonl").write_text("\n".join(json.dumps(c) for c in cands))
        import os
        cwd = os.getcwd()
        os.chdir(ROOT)
        try:
            site.build(out, d)
        finally:
            os.chdir(cwd)
        return out

    def test_card_tags_and_assets(self):
        out = self.build(ROWS, {"run_at": "2026-11-09T00:20:03+00:00", "gate": {"ok": True}, "counts": {}})
        html = (out / "index.html").read_text()
        t = Tags()
        t.feed(html)
        self.assertEqual(t.meta["og:title"], cards.TITLE)
        self.assertIn("20 million qubits in 2019", t.meta["og:description"])
        self.assertTrue(t.meta["og:url"].startswith("https://"))
        self.assertEqual(t.meta["twitter:card"], "summary")
        self.assertNotIn("og:image", t.meta)  # image choice is the owner's decision
        self.assertRegex(html, r"assets/css/base\.css\?v=[0-9a-f]{10}")
        self.assertEqual(html.count('class="dot'), 8)  # 3 + 3 (wide and narrow) + 1 + 1
        self.assertIn('class="proof is-sel"', html)
        self.assertNotIn("<nav", html)  # no navigation bar
        self.assertNotIn("github.com", html)
        self.assertTrue((out / "assets" / "fonts" / "Geist-Variable.woff2").exists())
        self.assertTrue((out / ".nojekyll").exists())
        self.assertNotIn("<style", html)

    def test_hostile_text_is_escaped(self):
        bad = dict(ROWS[0], title='<img src=x onerror=alert(1)> "t"', quote="<script>alert(1)</script>")
        out = self.build([bad], {"run_at": "2026-11-09T00:20:03+00:00"},
                         [{"tier": "B", "url": "https://arxiv.org/abs/1", "title": "<b>x</b>", "reason": "<i>r</i>"}])
        html = (out / "index.html").read_text()
        self.assertNotIn("<script>alert", html)
        self.assertNotIn("<img src=x", html)
        self.assertNotIn("<b>x</b>", html)

    def test_states(self):
        empty = (self.build([], None) / "index.html").read_text()
        self.assertIn("No verified estimates yet", empty)
        bad = (self.build(ROWS, {"run_at": "2026-11-09T00:00:00+00:00", "gate": {"ok": False},
                                 "source_errors": {"arxiv": "zero items"}}) / "index.html").read_text()
        self.assertIn("The last update had a problem", bad)
        self.assertIn('role="alert"', bad)


if __name__ == "__main__":
    unittest.main()
