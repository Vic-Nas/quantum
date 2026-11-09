import json
import os
import re
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from qtd import breakdate, cards, chart, present, site  # noqa: E402

try:
    import PIL  # noqa: F401
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False


def row(i, target, published, **kw):
    return {"id": f"arxiv:{i}#0", "kind": "attack", "target": target, "quote": f"quote {i}", "url": f"https://arxiv.org/abs/{i}",
            "title": f"Paper {i}", "published": published, **kw}


ROWS = [
    row("1905.09749", "rsa-2048", "2019-05-23", physical_qubits=20000000.0, runtime=8.0),
    row("2610.37839", "rsa-2048", "2026-10-27", physical_qubits=45000.0),
    row("2609.05625", "ecdlp-256", "2026-09-08", physical_qubits=19397.0, runtime=616.8),
    row("2607.13816", "ecdlp-256", "2026-07-15", logical_qubits=835.0),
    row("1512.04965", "aes-128", "2015-12-15", logical_qubits=2953.0),
]
HW = [
    {"id": f"page:ionq.com/roadmap#{i}", "kind": "hardware", "actor": "IonQ", "target_year": float(y), "physical_qubits": float(pq),
     "logical_qubits": float(lq), "quote": f"{y} {pq:,} physical qubits {lq:,} logical qubits", "url": "https://ionq.com/roadmap",
     "title": "IonQ | Roadmap", "added": "2026-11-09"}
    for i, (y, pq, lq) in enumerate([(2026, 100, 12), (2027, 10000, 800), (2028, 20000, 1600), (2029, 200000, 8000)])]
STATUS = {"run_at": "2026-11-09T00:20:03+00:00", "gate": {"ok": True}, "counts": {}}


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
        self.assertEqual(present.short_count(45000), "45,000")
        self.assertEqual(present.date_label("2026-10-27"), "27 Oct 2026")
        self.assertEqual(present.duration(168), "7 days")
        self.assertEqual(present.duration(1.25), "1.25 hours")

    def test_strip_dashes(self):
        em, en = "\u2014", "\u2013"
        self.assertEqual(present.strip_dashes(f"fast {em} but costly"), "fast; but costly")
        self.assertEqual(present.strip_dashes(f"fast{em}but costly"), "fast; but costly")
        self.assertEqual(present.strip_dashes(f"fast {en} but costly"), "fast; but costly")
        self.assertEqual(present.strip_dashes("fast -- but costly"), "fast; but costly")
        self.assertEqual(present.strip_dashes(f"2019{en}2026 and well-known"), f"2019{en}2026 and well-known")

    def test_series_and_headline(self):
        pts = present.series(ROWS, "rsa-2048")
        self.assertEqual([p["y"] for p in pts], [20000000.0, 45000.0])
        h = present.headline(ROWS, "rsa-2048")
        self.assertAlmostEqual(h["drop_pct"], 99.8, places=1)
        self.assertIsNone(present.headline(ROWS, "rsa-4096"))

    def test_clean_and_ids(self):
        self.assertEqual(present.paper_id("arxiv:2609.05625#4"), "arXiv 2609.05625")
        self.assertEqual(present.dom_id("arxiv:2609.05625#4"), "p-arxiv-2609-05625-4")
        self.assertNotIn("\n", present.clean("a\nb\x00c"))
        self.assertLessEqual(len(present.clean("x" * 400, 20)), 20)


class Chart(unittest.TestCase):
    def lines(self, narrow=False):
        return site.chart_lines(ROWS, HW, narrow)

    def svg(self, narrow=False):
        return chart.overview_svg(self.lines(narrow), breakdate.supply_points(HW, "physical_qubits"),
                                  breakdate.supply_points(HW, "logical_qubits"), 380 if narrow else 1100, 460, "label",
                                  present.year_frac("2026-11-09"), narrow)

    def test_every_attack_is_one_labelled_line_on_one_chart(self):
        svg = self.svg()
        self.assertEqual(svg.count("<svg"), 1)
        self.assertEqual(svg.count('class="atk"'), 3)  # 256-bit curves, RSA-2048, AES-128
        for name in ("RSA-2048", "256-bit curves", "AES-128"):
            self.assertIn(f">{name}<", svg)
        self.assertNotIn("nan", svg.lower())

    def test_each_line_is_read_against_its_own_kind_of_qubit(self):
        by = {ln["name"]: ln for ln in self.lines()}
        self.assertEqual((by["RSA-2048"]["metric"], by["RSA-2048"]["year"]), ("physical_qubits", 2029))  # 20,000 is short of 45,000
        self.assertEqual(by["256-bit curves"]["year"], 2028)
        self.assertFalse(by["AES-128"]["practical"])
        self.assertEqual(by["AES-128"]["when"], "not practical")

    def test_rings_only_for_practical_breaks_and_dots_for_every_machine(self):
        svg = self.svg()
        self.assertEqual(svg.count('class="cross"'), 2)  # not for AES, which is only weakened
        self.assertEqual(svg.count('class="dot '), 8)  # 4 physical and 4 logical announcements

    def test_labels_never_overlap(self):
        ys = chart.spread([100, 104, 108, 300, 301], 30, 10, 400)
        self.assertTrue(all(b - a >= 29.99 for a, b in zip(sorted(ys), sorted(ys)[1:])))
        self.assertEqual(chart.spread([5], 30, 10, 400), [10])  # stays inside the plot
        order = [ys.index(v) for v in sorted(ys)]
        self.assertEqual(order, [0, 1, 2, 3, 4])  # order is kept

    def test_narrow_version_has_short_labels(self):
        svg = self.svg(narrow=True)
        self.assertIn(">2029<", svg)
        visible = re.findall(r'class="sb"[^>]*>(.*?)</text>', svg)
        self.assertTrue(visible and all("physical" not in v and "logical" not in v for v in visible))  # just the year or the verdict


class BreakDate(unittest.TestCase):
    def test_earliest_year_a_big_enough_machine_is_announced(self):
        p = breakdate.earliest_path(ROWS, HW, "ecdlp-256")
        self.assertEqual(p["year"], 2028)  # 20,000 >= 19,397 physical and 1,600 >= 835 logical in the same year
        self.assertIsNone(breakdate.earliest_path(ROWS, [], "rsa-2048")["year"])
        self.assertEqual(breakdate.earliest_path(ROWS, [], "rsa-2048")["reason"], "no hardware announcements collected")


class Cards(unittest.TestCase):
    def test_home_card(self):
        c = cards.home_card(ROWS, HW, "2026-11-09", "https://example.com/q/")
        self.assertIn("Bitcoin and Ethereum keys 2028", c["description"])
        self.assertIn("RSA-2048 (websites, software updates) 2029", c["description"])
        self.assertIn("As of 2026-11-09", c["description"])
        self.assertLessEqual(len(c["description"]), 250)
        self.assertLessEqual(len(c["title"]), 60)
        img = cards.home_card(ROWS, HW, "2026-11-09", "https://example.com/q/", "https://example.com/q/assets/card.png")
        self.assertEqual((img["image"], img["image_width"], img["image_height"]), ("https://example.com/q/assets/card.png", 1200, 630))

    def test_empty_and_hostile(self):
        self.assertIn("No estimates", cards.home_card([], [], "", "https://e.com/")["description"])
        c = cards.home_card(ROWS, HW, "2026\n<script>alert(1)</script>", "https://e.com/")
        self.assertNotIn("\n", c["description"])


class BaseUrl(unittest.TestCase):
    def test_env_empty_and_slash(self):
        from unittest import mock
        with mock.patch.dict(os.environ, {"QTD_SITE_URL": ""}):
            self.assertEqual(site.base_url(), site.DEFAULT_URL)
        with mock.patch.dict(os.environ, {"QTD_SITE_URL": "https://x.example/app"}):
            self.assertEqual(site.base_url(), "https://x.example/app/")


class Build(unittest.TestCase):
    def build(self, rows, status=None, cands=None, hw=None, queue=None):
        d, out = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp()) / "site"
        (d / "attacks.json").write_text(json.dumps(rows))
        if hw is not None:
            (d / "hardware.json").write_text(json.dumps(hw))
        if status is not None:
            (d / "status.json").write_text(json.dumps(status))
        if queue is not None:
            (d / "queue.json").write_text(json.dumps(queue))
        if cands:
            (d / "candidates").mkdir()
            (d / "candidates" / "2026-11.jsonl").write_text("\n".join(json.dumps(c) for c in cands))
        cwd = os.getcwd()
        os.chdir(ROOT)
        try:
            site.build(out, d)
        finally:
            os.chdir(cwd)
        return out

    def test_one_chart_one_panel_and_nothing_else_stacked(self):
        out = self.build(ROWS, STATUS, hw=HW)
        html = (out / "index.html").read_text()
        self.assertEqual(html.count('class="tl ov"'), 2)  # one chart, in a wide and a narrow size
        self.assertEqual(html.count('class="proof is-sel"'), 1)
        self.assertEqual(html.count('class="atk"'), 6)
        for gone in ("role=\"tab\"", "<nav", "<table", "Everything affected", "How to read this", "How the size needed fell"):
            self.assertNotIn(gone, html)
        self.assertIn("Earliest announced path to a break", html)
        self.assertIn("Where you meet it", html)
        self.assertIn("If it breaks", html)
        self.assertNotIn("<style", html)
        self.assertTrue((out / "assets" / "favicon.svg").exists())
        self.assertFalse(list((out / "assets" / "fonts").glob("*.ttf")))

    def test_card_tags(self):
        out = self.build(ROWS, STATUS, hw=HW)
        t = Tags()
        t.feed((out / "index.html").read_text())
        self.assertEqual(t.meta["og:title"], cards.TITLE)
        self.assertIn("2028", t.meta["og:description"])
        self.assertTrue(t.meta["og:url"].startswith("https://"))
        if HAVE_PIL:
            self.assertEqual(t.meta["twitter:card"], "summary_large_image")
            self.assertEqual((out / "assets" / "card.png").read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    def test_without_pillow_the_card_falls_back_to_text_only(self):
        from unittest import mock
        with mock.patch.object(site.cardimg, "render", return_value=False):
            out = self.build(ROWS, STATUS, hw=HW)
        t = Tags()
        t.feed((out / "index.html").read_text())
        self.assertEqual(t.meta["twitter:card"], "summary")
        self.assertNotIn("og:image", t.meta)

    def test_proxy_result_is_listed_last_and_marked_or_later(self):
        proxy = row("2610.37839", "dlp-ff-512", "2026-10-27", physical_qubits=6656.0)
        out = self.build(ROWS + [proxy], STATUS, hw=HW)
        html = (out / "index.html").read_text()
        chips = re.findall(r'<span class="chip"><strong>(.*?)</strong> (.*?)</span>', html)
        self.assertEqual(chips[-1], ("2027 or later", "Finite-field DH"))
        self.assertEqual([c[0] for c in chips[:-1]], sorted(c[0] for c in chips[:-1]))

    def test_no_hardware_means_no_dates_not_made_up_ones(self):
        html = (self.build(ROWS, STATUS, hw=[]) / "index.html").read_text()
        self.assertNotIn('class="chip"', html)
        self.assertNotIn('class="cross"', html)
        self.assertIn("none announced", html)

    def test_hostile_text_is_escaped_and_dashes_removed(self):
        bad = dict(ROWS[2], title='<img src=x onerror=alert(1)> "t" \u2014 x', quote="<script>alert(1)</script> fast \u2014 but")
        out = self.build([bad] + ROWS[:2], STATUS, hw=HW)
        html = (out / "index.html").read_text()
        self.assertNotIn("<script>alert", html)
        self.assertNotIn("<img src=x", html)
        self.assertNotIn("\u2014", html)
        self.assertIn("fast; but", html)

    def test_served_data_has_no_em_dash_but_input_is_untouched(self):
        em = "\u2014"
        hw = [dict(HW[0], quote=f"We will deliver {em} by 2027")]
        out = self.build(ROWS, STATUS, hw=hw)
        served = (out / "data" / "hardware.json").read_text()
        self.assertNotIn(em, served)
        self.assertIn("We will deliver; by 2027", served)
        self.assertEqual(hw[0]["quote"], f"We will deliver {em} by 2027")

    def test_a_queued_paper_is_described_as_waiting_not_unconfirmed(self):
        cands = [{"id": "arxiv:9.9", "tier": "B", "url": "https://arxiv.org/abs/9.9", "title": "queued paper", "reason": "second opinion"}]
        html = (self.build(ROWS, STATUS, cands=cands, hw=HW, queue={"arxiv:9.9@seed": {"item": {}, "attempts": 1}}) / "index.html").read_text()
        self.assertIn("1 paper is waiting to be re-checked", html)
        self.assertNotIn(">queued paper<", html)

    def test_states(self):
        self.assertIn("No verified estimates yet", (self.build([], None) / "index.html").read_text())
        bad = (self.build(ROWS, {**STATUS, "gate": {"ok": False}, "source_errors": {"arxiv": "zero items"}}, hw=HW) / "index.html").read_text()
        self.assertIn("The last update had a problem", bad)
        self.assertIn('role="alert"', bad)


if __name__ == "__main__":
    unittest.main()
