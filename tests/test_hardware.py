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


class Month(unittest.TestCase):
    Q = "IonQ will deliver 10,000 physical qubits in June 2027, and 40,000 in 2028."
    SRC = "Roadmap. " + Q

    def est(self, month, year="2027", quote=None):
        return {"kind": "hardware", "estimates": [{"quote": quote or self.Q, "fields": {
            "physical_qubits": "10,000", "target_year": year, "target_month": month}}]}

    def month(self, ex):
        res = verify(ex, self.SRC, True, {"actor": "IonQ"})["ok_estimates"]
        return res[0]["values"].get("target_month")

    def test_a_month_next_to_the_year_is_kept_as_a_number(self):
        self.assertEqual(self.month(self.est("June")), 6)
        self.assertEqual(self.month(self.est("Jun")), 6)

    def test_a_wrong_or_unattached_month_is_dropped_without_sinking_the_claim(self):
        self.assertIsNone(self.month(self.est("March")))  # not in the quote
        q = "We may deliver 10,000 physical qubits in 2027."
        self.assertIsNone(verify(self.est("May", quote=q), q, True, {"actor": "IonQ"})["ok_estimates"][0]["values"].get("target_month"))
        self.assertEqual(self.month(self.est("June", year="2027")), 6)

    def test_models_need_not_agree_on_the_month(self):
        from qtd.verify import agree
        base = {"actor": "IonQ", "physical_qubits": 10000.0, "target_year": 2027.0}
        self.assertTrue(agree({**base, "target_month": 6}, base))
        self.assertTrue(agree({**base, "target_month": 6}, {**base, "target_month": 5}))

    def test_month_extraction_adds_no_model_calls(self):
        calls = []

        def fn(role, f, exclude=None):
            calls.append(role)
            ex = self.est("June")
            return ex, ("gemini-3.5-flash-lite" if role == "primary" else "gemini-3.1-flash-lite")
        pipeline.DATA = Path(tempfile.mkdtemp())
        with mock.patch.object(llm, "call_chain", fn):
            r = pipeline.run_hardware(items=[{"id": "page:x", "version": "1", "source": "page", "url": "https://ionq.com/roadmap",
                                              "actor": "IonQ", "title": "Roadmap", "text": self.Q, "published": "", "updated": ""}])
        self.assertEqual(sorted(calls), ["primary", "secondary"])  # one pair, same as before the month field existed
        self.assertEqual(json.loads((pipeline.DATA / "hardware.json").read_text())[0]["target_month"], 6)

    def test_an_existing_row_gains_the_month_only_from_the_same_quote(self):
        pipeline.DATA = Path(tempfile.mkdtemp())
        row = {"id": "p#0", "kind": "hardware", "actor": "IonQ", "target_year": 2027.0, "physical_qubits": 10000.0, "quote": self.Q}
        (pipeline.DATA / "hardware.json").write_text(json.dumps([row, {**row, "id": "p#1", "target_year": 2030.0, "quote": "other"}]))

        def fn(role, f, exclude=None):
            return self.est("June"), ("gemini-3.5-flash-lite" if role == "primary" else "gemini-3.1-flash-lite")
        with mock.patch.object(llm, "call_chain", fn):
            r = pipeline.run_hardware(items=[{"id": "page:x", "version": "2", "source": "page", "url": "https://ionq.com/roadmap",
                                              "actor": "IonQ", "title": "Roadmap", "text": self.Q, "published": "", "updated": ""}])
        rows = json.loads((pipeline.DATA / "hardware.json").read_text())
        self.assertEqual((r["applied"], r.get("month_added")), (0, 1))
        self.assertEqual(rows[0]["target_month"], 6)
        self.assertNotIn("target_month", rows[1])


class Dates(unittest.TestCase):
    ATTACK = [{"id": "a#0", "target": "rsa-2048", "physical_qubits": 100.0, "published": "2026-01-01"}]

    def test_a_month_makes_a_machine_earlier_than_a_year_only_one(self):
        rows = [hw("A", 2028, 200), {**hw("B", 2028, 200), "target_month": 3}]
        p = breakdate.earliest_path(self.ATTACK, rows, "rsa-2048")
        self.assertEqual((p["year"], p["month"], p["supply"]["actor"]), (2028, 3, "B"))
        self.assertAlmostEqual(p["when"], 2028.25)

    def test_without_months_everything_is_as_before(self):
        p = breakdate.earliest_path(self.ATTACK, [hw("A", 2028, 200)], "rsa-2048")
        self.assertEqual((p["year"], p["month"], p["when"]), (2028, None, 2029.0))
        self.assertEqual(breakdate.supply_points([hw("A", 2028, 200)], "physical_qubits")[0]["x"], 2028.5)

    def test_a_month_moves_the_machine_on_the_axis(self):
        pts = breakdate.supply_points([{**hw("A", 2028, 200), "target_month": 1}], "physical_qubits")
        self.assertAlmostEqual(pts[0]["x"], 2028 + 0.5 / 12)


if __name__ == "__main__":
    unittest.main()
