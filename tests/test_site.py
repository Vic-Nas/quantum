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
    {"id": "arxiv:2609.05625#4", "kind": "attack", "target": "ecdlp-256", "physical_qubits": 19397.0, "runtime": 616.8,
     "quote": "q1", "url": "https://arxiv.org/abs/2609.05625", "title": "ECDLP paper", "added": "2026-11-09"},
    {"id": "arxiv:2610.37839#3", "kind": "attack", "target": "rsa-2048", "physical_qubits": 45000.0,
     "quote": "q2", "url": "https://arxiv.org/abs/2610.37839", "title": "RSA paper", "added": "2026-11-09"},
    {"id": "arxiv:2607.13816#7", "kind": "attack", "target": "ecdlp-256", "logical_qubits": 835.0,
     "quote": "q3", "url": "https://arxiv.org/abs/2607.13816", "title": "Logical paper", "added": "2026-11-09"},
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
    def test_duration(self):
        self.assertEqual(present.duration(168), "7 days")
        self.assertEqual(present.duration(616.8), "25.7 days")
        self.assertEqual(present.duration(1.25), "1.25 hours")
        self.assertEqual(present.duration(1), "1 hour")
        self.assertEqual(present.duration(0.35), "21 minutes")
        self.assertEqual(present.duration(None), "")

    def test_best_by_target(self):
        b = present.best_by_target(ROWS)
        self.assertEqual(b["ecdlp-256"]["physical"]["physical_qubits"], 19397.0)
        self.assertEqual(b["ecdlp-256"]["logical"]["logical_qubits"], 835.0)
        self.assertIsNone(b["rsa-2048"]["logical"])

    def test_paper_id_and_clean(self):
        self.assertEqual(present.paper_id("arxiv:2609.05625#4"), "arXiv 2609.05625")
        self.assertEqual(present.clean("a\nb\x00c\x07" + "x" * 400, 20).count("\n"), 0)
        self.assertLessEqual(len(present.clean("x" * 400, 20)), 20)


class Cards(unittest.TestCase):
    def test_home_card(self):
        c = cards.home_card(ROWS, "2026-11-09", "https://example.com/q/")
        self.assertIn("As of 2026-11-09", c["description"])
        self.assertIn("RSA-2048 45,000", c["description"])
        self.assertTrue(c["url"].startswith("https://"))
        self.assertLessEqual(len(c["description"]), 250)
        self.assertNotRegex(c["description"].lower(), r"\bago\b|\bminutes? ago|just now")

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
        self.assertEqual(t.meta["og:title"], "Cheapest known quantum attacks")
        self.assertIn("RSA-2048 45,000", t.meta["og:description"])
        self.assertTrue(t.meta["og:url"].startswith("https://"))
        self.assertEqual(t.meta["twitter:card"], "summary")
        self.assertNotIn("og:image", t.meta)  # image choice is the owner's decision
        self.assertRegex(html, r"assets/css/base\.css\?v=[0-9a-f]{10}")
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
        self.assertIn("No estimates yet", empty)
        self.assertIn("No run yet", empty)
        bad = (self.build(ROWS, {"run_at": "2026-11-09T00:00:00+00:00", "gate": {"ok": False},
                                 "source_errors": {"arxiv": "zero items"}}) / "index.html").read_text()
        self.assertIn("Needs attention", bad)
        self.assertIn('role="alert"', bad)


if __name__ == "__main__":
    unittest.main()
