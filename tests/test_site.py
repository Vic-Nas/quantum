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
        em, en = "—", "–"
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

    def test_year_label(self):
        self.assertEqual(present.year_label(2028), "2028")
        self.assertEqual(present.year_label(2028, 3), "Mar 2028")
        self.assertEqual(present.year_label(2028, None), "2028")
        self.assertEqual(present.year_label(2028, 12), "Dec 2028")


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
        self.assertEqual(svg.count('class="atk"'), 3)
        for name in ("RSA-2048", "256-bit curves", "AES-128"):
            self.assertIn(f">{name}<", svg)
        self.assertNotIn("nan", svg.lower())

    def test_each_line_is_read_against_its_own_kind_of_qubit(self):
        by = {ln["name"]: ln for ln in self.lines()}
        self.assertEqual((by["RSA-2048"]["metric"], by["RSA-2048"]["year"]), ("physical_qubits", 2029))
        self.assertEqual(by["256-bit curves"]["year"], 2028)
        self.assertFalse(by["AES-128"]["practical"])
        self.assertEqual(by["AES-128"]["when"], "not practical")

    def test_rings_only_for_practical_breaks_and_dots_for_every_machine(self):
        svg = self.svg()
        self.assertEqual(svg.count('class="cross"'), 2)
        self.assertEqual(svg.count('class="dot '), 8)

    def test_labels_never_overlap(self):
        ys = chart.spread([100, 104, 108, 300, 301], 30, 10, 400)
        self.assertTrue(all(b - a >= 29.99 for a, b in zip(sorted(ys), sorted(ys)[1:])))
        self.assertEqual(chart.spread([5], 30, 10, 400), [10])
        order = [ys.index(v) for v in sorted(ys)]
        self.assertEqual(order, [0, 1, 2, 3, 4])

    def test_narrow_version_has_short_labels(self):
        svg = self.svg(narrow=True)
        self.assertIn(">2029<", svg)
        visible = re.findall(r'class="sb"[^>]*>(.*?)</text>', svg)
        self.assertTrue(visible and all("physical" not in v and "logical" not in v for v in visible))


class BreakDate(unittest.TestCase):
    def test_earliest_year_a_big_enough_machine_is_announced(self):
        p = breakdate.earliest_path(ROWS, HW, "ecdlp-256")
        self.assertEqual(p["year"], 2028)
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

    def countdown(self, html):
        out = []
        for block in re.findall(r'<a class="row[^"]*".*?</a>', html, re.S):
            title = re.search(r"<strong>(.*?)</strong>", block).group(1)
            year = re.search(r"<b>(.*?)</b>", block) or re.search(r'class="safe">(.*?)<', block)
            out.append((title, year.group(1) if year else ""))
        return out

    def test_multi_page_structure(self):
        out = self.build(ROWS, STATUS, hw=HW)
        self.assertTrue((out / "index.html").exists())
        self.assertTrue((out / "research" / "index.html").exists())
        self.assertTrue((out / "hardware" / "index.html").exists())
        self.assertTrue((out / "chart" / "index.html").exists())
        self.assertTrue((out / "threats" / "bitcoin" / "index.html").exists())
        self.assertTrue((out / "threats" / "websites" / "index.html").exists())

    def test_nav_on_every_page(self):
        out = self.build(ROWS, STATUS, hw=HW)
        for page in ("index.html", "research/index.html", "hardware/index.html", "chart/index.html"):
            html = (out / page).read_text()
            self.assertIn('class="top-nav"', html)
            self.assertIn('>Home<', html)
            self.assertIn('>Research<', html)

    def test_home_has_countdown_and_card_grid(self):
        out = self.build(ROWS, STATUS, hw=HW)
        html = (out / "index.html").read_text()
        self.assertIn('class="cd"', html)
        self.assertIn('class="threat-card"', html)
        self.assertIn('View details', html)
        self.assertNotIn('class="d-nav"', html)
        self.assertNotIn('class="d-panels"', html)

    def test_countdown_links_to_threat_pages(self):
        out = self.build(ROWS, STATUS, hw=HW)
        html = (out / "index.html").read_text()
        hrefs = re.findall(r'<a class="row[^"]*" href="([^"]+)"', html)
        self.assertTrue(hrefs)
        for href in hrefs:
            self.assertTrue(href.startswith("threats/"))
            page_path = out / href / "index.html"
            self.assertTrue(page_path.exists(), f"Missing threat page: {href}")

    def test_front_page_answers_the_bitcoin_question_first(self):
        proxy = row("2610.37839", "dlp-ff-512", "2026-10-27", physical_qubits=6656.0)
        html = (self.build(ROWS + [proxy], STATUS, hw=HW) / "index.html").read_text()
        rows = self.countdown(html)
        self.assertEqual(rows[0], ("Bitcoin, Ethereum and crypto wallets", "2028"))
        self.assertIn('class="row first"', html)
        self.assertEqual(dict(rows)["Websites and software updates"], "2029")
        self.assertEqual(dict(rows)["Older VPN setups"], "2027 or later")
        self.assertEqual(dict(rows)["Disk encryption and passwords"], "Safe in practice")

    def test_threat_page_content(self):
        out = self.build(ROWS, STATUS, hw=HW)
        html = (out / "threats" / "bitcoin" / "index.html").read_text()
        self.assertIn("Bitcoin, Ethereum and crypto wallets", html)
        self.assertIn("19,397 physical qubits", html)
        self.assertIn("Read the paper", html)
        self.assertIn("Where you meet it", html)
        self.assertIn("If it breaks", html)
        self.assertIn("The papers (", html)
        self.assertIn("Needed today", html)
        self.assertIn("Machine announced", html)
        self.assertIn("All threats", html)

    def test_threat_page_has_hardware_section(self):
        out = self.build(ROWS, STATUS, hw=HW)
        html = (out / "threats" / "bitcoin" / "index.html").read_text()
        self.assertIn("Machines big enough", html)
        self.assertIn("IonQ", html)
        self.assertIn("Could break: 256-bit curves", html)
        self.assertEqual(html.count("could break: ") + html.count("Could break: "), 1)  # only where the list grows

    def test_research_page_lists_all_papers(self):
        out = self.build(ROWS, STATUS, hw=HW)
        html = (out / "research" / "index.html").read_text()
        self.assertIn("Every paper we track", html)
        self.assertIn("<table", html)
        self.assertIn("256-bit elliptic curve", html)
        self.assertIn("RSA-2048", html)
        for r in ROWS:
            self.assertIn(r["url"], html)

    def test_hardware_page_shows_vendors(self):
        out = self.build(ROWS, STATUS, hw=HW)
        html = (out / "hardware" / "index.html").read_text()
        self.assertIn("Machines vendors plan to build", html)
        self.assertIn("Could break", html)
        self.assertIn("IonQ", html)

    def test_chart_page_has_full_chart(self):
        out = self.build(ROWS, STATUS, hw=HW)
        html = (out / "chart" / "index.html").read_text()
        self.assertIn("Machines versus attacks", html)
        self.assertEqual(html.count('class="tl ov"'), 2)
        self.assertNotIn("<details", html)

    def test_safe_threat_page_has_no_source(self):
        out = self.build(ROWS, STATUS, hw=HW)
        html = (out / "threats" / "disk-encryption" / "index.html").read_text()
        self.assertNotIn("Read the paper", html)
        self.assertIn("Where you meet it", html)
        self.assertIn("Safe in practice", html)

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

    def test_hostile_text_is_escaped_and_dashes_removed(self):
        bad = dict(ROWS[2], title='<img src=x onerror=alert(1)> "t" — x', quote="<script>alert(1)</script> fast — but")
        out = self.build([bad] + ROWS[:2], STATUS, hw=HW)
        home = (out / "index.html").read_text()
        self.assertNotIn("<script>alert", home)
        self.assertNotIn("<img src=x", home)
        self.assertNotIn("—", home)
        threat = (out / "threats" / "bitcoin" / "index.html").read_text()
        self.assertNotIn("<script>alert", threat)
        self.assertIn("fast; but", threat)

    def test_em_dashes_stripped_and_no_data_dir_served(self):
        em = "—"
        rows = [dict(ROWS[0], quote=f"fast{em} but expensive")]
        out = self.build(rows, STATUS, hw=HW)
        threat_slug = list((out / "threats").iterdir())[0].name
        html = (out / "threats" / threat_slug / "index.html").read_text()
        self.assertNotIn(em, html)
        self.assertIn("fast; but expensive", html)
        self.assertEqual(rows[0]["quote"], f"fast{em} but expensive")
        self.assertFalse((out / "data").exists())

    def test_a_queued_paper_is_described_as_waiting_not_unconfirmed(self):
        cands = [{"id": "arxiv:9.9", "tier": "B", "url": "https://arxiv.org/abs/9.9", "title": "queued paper", "reason": "second opinion"}]
        out = self.build(ROWS, STATUS, cands=cands, hw=HW, queue={"arxiv:9.9@seed": {"item": {}, "attempts": 1}})
        html = (out / "research" / "index.html").read_text()
        self.assertIn("1 paper is waiting to be re-checked", html)
        self.assertNotIn(">queued paper<", html)

    def test_states(self):
        self.assertIn("No verified estimates yet", (self.build([], None) / "index.html").read_text())
        bad = (self.build(ROWS, {**STATUS, "gate": {"ok": False}, "source_errors": {"arxiv": "zero items"}}, hw=HW) / "index.html").read_text()
        self.assertNotIn("The last update had a problem", bad)
        self.assertNotIn('role="alert"', bad)
        self.assertNotIn("zero items", bad)

    def test_month_precision_in_threat_page(self):
        hw_month = [dict(HW[2], target_month=6)]
        out = self.build(ROWS, STATUS, hw=hw_month)
        html = (out / "threats" / "bitcoin" / "index.html").read_text()
        self.assertIn("Jun 2028", html)

    def test_progress_chart_on_threat_page(self):
        extra = row("2302.06639", "ecdlp-256", "2023-02-13", physical_qubits=126133.0, runtime=9.0)
        out = self.build(ROWS + [extra], STATUS, hw=HW)
        html = (out / "threats" / "bitcoin" / "index.html").read_text()
        self.assertIn('class="prog"', html)
        self.assertIn("<svg", html)
        self.assertIn("How many qubits an attack needs, over time", html)
        self.assertIn("down 85%", html)
        self.assertIn("first estimate", html)
        self.assertIn("Physical qubits needed", html)

    def test_inner_page_og_tags(self):
        out = self.build(ROWS, STATUS, hw=HW)
        t = Tags()
        t.feed((out / "research" / "index.html").read_text())
        self.assertIn("Research", t.meta["og:title"])
        t2 = Tags()
        t2.feed((out / "threats" / "bitcoin" / "index.html").read_text())
        self.assertIn("Bitcoin", t2.meta["og:title"])


class Papers(unittest.TestCase):
    def test_pct_label_never_rounds_up_to_a_false_100(self):
        self.assertEqual(present.pct_label(0.846), "85%")
        self.assertEqual(present.pct_label(0.998), "99.8%")

    def test_one_row_per_paper_with_its_smallest_figures_and_the_drop_it_caused(self):
        rows = [row("1.1", "ecdlp-256", "2020-01-01", physical_qubits=1000.0),
                {**row("2.2", "ecdlp-256", "2021-01-01", physical_qubits=400.0), "id": "arxiv:2.2#0"},
                {**row("2.2", "ecdlp-256", "2021-01-01", physical_qubits=300.0, logical_qubits=50.0), "id": "arxiv:2.2#1"},
                row("3.3", "ecdlp-256", "2022-01-01", physical_qubits=350.0)]
        out = present.paper_rows(rows, {"ecdlp-256"})
        self.assertEqual([r["id"] for r in out], ["arxiv:3.3", "arxiv:2.2", "arxiv:1.1"])  # newest first, one per paper
        by = {r["id"]: r for r in out}
        self.assertEqual(by["arxiv:2.2"]["physical_qubits"], 300.0)
        self.assertAlmostEqual(by["arxiv:2.2"]["phys_drop"], 0.7)
        self.assertIsNone(by["arxiv:3.3"]["phys_drop"])  # 350 is not below the best so far (300)
        self.assertIsNone(by["arxiv:1.1"]["phys_drop"])  # the first estimate has nothing to beat

    def test_series_records_carry_the_drop(self):
        pts = present.series([row("1.1", "rsa-2048", "2020-01-01", physical_qubits=1000.0),
                              row("2.2", "rsa-2048", "2021-01-01", physical_qubits=250.0)], "rsa-2048")
        self.assertIsNone(pts[0]["drop"])
        self.assertAlmostEqual(pts[1]["drop"], 0.75)


class Header(unittest.TestCase):
    def test_updated_shows_the_time_and_github_link(self):
        from qtd.present import datetime_label
        self.assertEqual(datetime_label("2026-11-09T05:21:03+00:00"), "9 Nov 2026, 05:21 UTC")
        self.assertEqual(datetime_label("2026-11-09"), "9 Nov 2026")
        self.assertEqual(datetime_label(""), "")


if __name__ == "__main__":
    unittest.main()
