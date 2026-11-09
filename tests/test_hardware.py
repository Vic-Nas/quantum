import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from qtd import breakdate, llm, pipeline, sources, stages  # noqa: E402
from qtd.verify import verify  # noqa: E402

PAGE = """<html><head><title>Vendor | Roadmap</title><style>.a{}</style><script>var x=1;</script></head><body>
<nav>Menu</nav><h1>Roadmap</h1><p>We will deliver 10,000 physical qubits and 800 logical qubits in 2027.</p>
<div>Later</div></body></html>"""


class Page(unittest.TestCase):
    def test_html_to_text_drops_scripts_and_keeps_blocks(self):
        title, text = sources.html_to_text(PAGE)
        self.assertEqual(title, "Vendor | Roadmap")
        self.assertIn("We will deliver 10,000 physical qubits and 800 logical qubits in 2027.", text.split("\n"))
        self.assertNotIn("var x", text)
        self.assertNotIn(".a{}", text)

    def test_chunks_split_on_lines_and_lose_nothing(self):
        text = "\n".join(f"line {i} " + "x" * 50 for i in range(100))
        parts = stages.chunks(text, size=500)
        self.assertGreater(len(parts), 5)
        self.assertTrue(all(len(p) <= 520 for p in parts))
        self.assertEqual("".join(parts).replace("\n", ""), text.replace("\n", ""))

    def test_allowlist_covers_the_vendors(self):
        self.assertTrue(sources.is_allowlisted("https://ionq.com/roadmap"))
        self.assertTrue(sources.is_allowlisted("https://www.ibm.com/quantum/technology"))
        self.assertFalse(sources.is_allowlisted("https://ionq.com.evil.example/roadmap"))


class Verify(unittest.TestCase):
    SRC = "Roadmap. We will deliver 10,000 physical qubits and 800 logical qubits in 2027."

    def est(self, **fields):
        return {"kind": "hardware", "estimates": [{"quote": "We will deliver 10,000 physical qubits and 800 logical qubits in 2027.",
                                                    "fields": fields}]}

    def test_needs_a_year_and_a_size(self):
        ok = verify(self.est(physical_qubits="10,000", logical_qubits="800", target_year="2027"), self.SRC, True, {"actor": "IonQ"})
        self.assertTrue(ok["ok_estimates"], ok["estimates"])
        self.assertEqual(ok["ok_estimates"][0]["values"]["actor"], "IonQ")
        self.assertEqual(ok["ok_estimates"][0]["values"]["target_year"], 2027.0)
        self.assertFalse(verify(self.est(physical_qubits="10,000"), self.SRC, True, {"actor": "IonQ"})["ok_estimates"])  # no year
        self.assertFalse(verify(self.est(target_year="2027"), self.SRC, True, {"actor": "IonQ"})["ok_estimates"])  # no size

    def test_invented_number_or_year_is_rejected(self):
        self.assertFalse(verify(self.est(physical_qubits="50,000", target_year="2027"), self.SRC, True, {"actor": "IonQ"})["ok_estimates"])
        self.assertFalse(verify(self.est(physical_qubits="10,000", target_year="2031"), self.SRC, True, {"actor": "IonQ"})["ok_estimates"])


ATTACK = [{"id": "p#0", "target": "rsa-2048", "physical_qubits": 22593.0, "published": "2026-10-27"},
          {"id": "p#1", "target": "rsa-2048", "physical_qubits": 45000.0, "published": "2026-10-27"},
          {"id": "q#0", "target": "ecdlp-256", "logical_qubits": 835.0, "physical_qubits": 19397.0, "published": "2026-09-04"}]


def hw(actor, year, physical=None, logical=None):
    return {"id": f"{actor}{year}", "actor": actor, "target_year": year, "physical_qubits": physical, "logical_qubits": logical}


class BreakDate(unittest.TestCase):
    def test_earliest_year_a_big_enough_machine_is_announced(self):
        rows = [hw("A", 2027, 10000), hw("A", 2028, 20000), hw("A", 2029, 200000)]
        p = breakdate.earliest_path(ATTACK, rows, "rsa-2048")
        self.assertEqual((p["year"], p["metric"], p["need"]), (2029, "physical_qubits", 22593.0))  # 20,000 is short of 22,593

    def test_uses_the_cheapest_requirement_and_the_earlier_metric(self):
        rows = [hw("A", 2028, 20000, 1600), hw("B", 2033, None, 2000)]
        p = breakdate.earliest_path(ATTACK, rows, "ecdlp-256")
        self.assertEqual(p["year"], 2028)  # 20,000 >= 19,397 physical, and 1,600 >= 835 logical in the same year

    def test_logical_metric_alone_can_set_the_date(self):
        rows = [hw("B", 2029, None, 200), hw("B", 2033, None, 2000)]
        p = breakdate.earliest_path(ATTACK, rows, "ecdlp-256")
        self.assertEqual((p["year"], p["metric"]), (2033, "logical_qubits"))

    def test_reasons_when_there_is_no_date(self):
        self.assertEqual(breakdate.earliest_path(ATTACK, [], "rsa-2048")["reason"], "no hardware announcements collected")
        self.assertEqual(breakdate.earliest_path(ATTACK, [hw("A", 2027, 100)], "rsa-2048")["reason"], "no announced machine is large enough yet")
        self.assertEqual(breakdate.earliest_path(ATTACK, [hw("A", 2027, 100)], "rsa-3072")["reason"], "no published requirement")
        self.assertIsNone(breakdate.earliest_path([], [], "rsa-2048")["year"])

    def test_supply_points_mark_records(self):
        pts = breakdate.supply_points([hw("A", 2028, 20000), hw("A", 2027, 10000), hw("B", 2029, 15000)], "physical_qubits")
        self.assertEqual([(p["year"], p["record"]) for p in pts], [(2027, True), (2028, True), (2029, False)])


def item(version="v1"):
    title, text = sources.html_to_text(PAGE)
    return {"id": "page:vendor.example/roadmap", "version": version, "source": "page", "url": "https://ionq.com/roadmap",
            "actor": "IonQ", "title": title, "text": text, "published": "", "updated": ""}


def chain(fail=False, agree=True):
    quote = "We will deliver 10,000 physical qubits and 800 logical qubits in 2027."

    def fn(role, f, exclude=None):
        if fail:
            raise llm.LLMError("down")
        pq = "10,000" if (role == "primary" or agree) else "9,999"
        ex = {"kind": "hardware", "estimates": [{"quote": quote, "fields": {"physical_qubits": pq, "logical_qubits": "800", "target_year": "2027"}}]}
        return ex, ("gemini-3.5-flash-lite" if role == "primary" else "gemini-3.1-flash-lite")
    return fn


class Run(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        pipeline.DATA = Path(self.tmp)

    def read(self, name):
        return json.loads((Path(self.tmp) / name).read_text())

    def test_agreed_claim_is_applied_once_and_unchanged_pages_are_skipped(self):
        with mock.patch.object(llm, "call_chain", chain()):
            r = pipeline.run_hardware(items=[item()])
            self.assertEqual((r["changed"], r["applied"]), (1, 1))
            row = self.read("hardware.json")[0]
            self.assertEqual((row["actor"], row["target_year"], row["physical_qubits"], row["logical_qubits"]), ("IonQ", 2027.0, 10000.0, 800.0))
            self.assertIn("800 logical qubits", row["quote"])
            r2 = pipeline.run_hardware(items=[item()])  # same page version: nothing to do
            self.assertEqual(r2["changed"], 0)
            r3 = pipeline.run_hardware(items=[item("v2")])  # page changed, same claim: not duplicated
            self.assertEqual((r3["changed"], r3["applied"]), (1, 0))
        self.assertEqual(len(self.read("hardware.json")), 1)

    def test_disagreement_is_not_applied(self):
        with mock.patch.object(llm, "call_chain", chain(agree=False)):
            r = pipeline.run_hardware(items=[item()])
        self.assertEqual(r["applied"], 0)

    def test_models_down_leaves_the_page_pending_until_it_succeeds(self):
        with mock.patch.object(llm, "call_chain", chain(fail=True)):
            r = pipeline.run_hardware(items=[item()])
        self.assertEqual((r["unavailable"], r["applied"]), (1, 0))
        self.assertEqual(self.read("hw_seen.json"), {})
        self.assertEqual([p["id"] for p in self.read("hw_pending.json")], ["page:vendor.example/roadmap"])  # the frequent run retries this
        with mock.patch.object(llm, "call_chain", chain()):
            self.assertEqual(pipeline.run_hardware(items=[item()])["applied"], 1)
        self.assertEqual(self.read("hw_pending.json"), [])  # cleared once it worked


if __name__ == "__main__":
    unittest.main()
