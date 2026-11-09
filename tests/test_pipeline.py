import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from qtd import llm, pipeline  # noqa: E402

TEXT = ("We estimate that 2048-bit RSA integers can be factored in less than a week using "
        "fewer than a million noisy qubits. Shor factoring needs logical qubits and Toffoli gates.")
QUOTE = ("We estimate that 2048-bit RSA integers can be factored in less than a week using "
         "fewer than a million noisy qubits.")


def item(n=1):
    return {"id": f"arxiv:9999.{n:05d}", "version": "1", "source": "arxiv", "url": f"https://arxiv.org/abs/9999.{n:05d}",
            "title": "Shor RSA resource estimate", "text": TEXT, "published": "2026-11-01", "updated": ""}


def fake_chain(fail=False, same_family=False, relevant=True):
    def chain(role, fn, exclude=None):
        if fail:
            raise llm.LLMError("503 unavailable")
        if role == "coarse":
            return {"relevant": relevant, "reason": "x"}, "gemma-4-26b-a4b-it"
        ex = {"kind": "attack", "estimates": [{"quote": QUOTE, "fields": {"target": "RSA-2048", "physical_qubits": "a million"}}]}
        model = {"primary": "gemini-3.5-flash-lite", "secondary": "gemini-3.5-flash-lite" if same_family else "gemini-3.1-flash-lite"}[role]
        return ex, model
    return chain


class Pipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        pipeline.DATA = Path(self.tmp)
        (Path(self.tmp) / "gold").mkdir()
        (Path(self.tmp) / "gold" / "gold.jsonl").write_text("")

    def read(self, name):
        return json.loads((Path(self.tmp) / name).read_text())

    def test_two_families_auto_apply(self):
        with mock.patch.object(llm, "call_chain", fake_chain()), mock.patch.object(pipeline, "canary", lambda: {"ok": True}):
            r = pipeline.run(items=[item()])
        self.assertEqual((r["counts"]["A"], r["auto_applied"], r["held"]), (1, 1, 0))
        row = self.read("attacks.json")[0]
        self.assertEqual((row["target"], row["physical_qubits"]), ("rsa-2048", 1e6))
        self.assertIn("rsa", row["quote"].lower())

    def test_the_same_model_twice_is_not_enough(self):
        with mock.patch.object(llm, "call_chain", fake_chain(same_family=True)), \
                mock.patch.dict(llm.CHAINS, {"secondary": ["gemini-3.5-flash-lite"]}):
            r = pipeline.run(items=[item()])
        self.assertEqual((r["counts"]["A"], r["counts"]["B"], r["auto_applied"]), (0, 1, 0))

    def test_failed_canary_holds_everything(self):
        with mock.patch.object(llm, "call_chain", fake_chain()), mock.patch.object(pipeline, "canary", lambda: {"ok": False}):
            r = pipeline.run(items=[item()])
        self.assertEqual((r["auto_applied"], r["held"]), (0, 1))
        self.assertEqual(self.read("attacks.json"), [])
        self.assertEqual(len(list((Path(self.tmp) / "proposals").glob("*.json"))), 1)

    def test_cap_holds_burst(self):
        with mock.patch.object(llm, "call_chain", fake_chain()), mock.patch.object(pipeline, "canary", lambda: {"ok": True}):
            r = pipeline.run(items=[item(n) for n in range(1, 6)])
        self.assertEqual((r["auto_applied"], r["held"]), (0, 5))

    def test_models_down_queues_then_recovers_then_gives_up(self):
        with mock.patch.object(llm, "call_chain", fake_chain(fail=True)):
            r = pipeline.run(items=[item()])
        self.assertEqual((r["counts"]["retry"], r["queue_size"]), (1, 1))
        self.assertEqual(self.read("seen.json"), [])  # not lost
        with mock.patch.object(llm, "call_chain", fake_chain()), mock.patch.object(pipeline, "canary", lambda: {"ok": True}):
            r = pipeline.run(items=[])  # retried from the queue, no refetch needed
        self.assertEqual((r["processed"], r["queue_size"], r["auto_applied"]), (1, 0, 1))
        with mock.patch.object(llm, "call_chain", fake_chain(fail=True)):
            for _ in range(pipeline.MAX_ATTEMPTS):
                r = pipeline.run(items=[item(2)])
        self.assertEqual((r["counts"]["gave_up"], r["queue_size"]), (1, 0))

    def test_fallback_second_opinion_is_retried_not_final(self):
        # secondary came from a fallback model (not the chain's first choice) and did not confirm
        def chain(role, fn, exclude=None):
            if role == "coarse":
                return {"relevant": True, "reason": "x"}, "gemma-4-26b-a4b-it"
            if role == "primary":
                return fake_chain()("primary", fn)
            return {"kind": "attack", "estimates": []}, llm.CHAINS["secondary"][1]
        with mock.patch.object(llm, "call_chain", chain):
            r = pipeline.run(items=[item()])
        self.assertEqual((r["counts"]["retry"], r["queue_size"], r["counts"]["B"]), (1, 1, 0))
        self.assertEqual(self.read("seen.json"), [])

    def test_dry_run_writes_nothing(self):
        with mock.patch.object(llm, "call_chain", fake_chain()):
            pipeline.run(items=[item()], dry=True)
        self.assertFalse((Path(self.tmp) / "seen.json").exists())

    def test_irrelevant_dropped_by_coarse(self):
        with mock.patch.object(llm, "call_chain", fake_chain(relevant=False)):
            r = pipeline.run(items=[item()])
        self.assertEqual(r["counts"]["drop"], 1)


class Retry(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        pipeline.DATA = Path(self.tmp)

    def test_idle_when_queue_is_empty_and_never_touches_models(self):
        with mock.patch.object(llm, "call_chain", side_effect=AssertionError("models must not be called")):
            self.assertTrue(pipeline.retry()["idle"])
        self.assertFalse((Path(self.tmp) / "status.json").exists())  # does not overwrite the daily status

    def test_processes_only_the_queue(self):
        (Path(self.tmp) / "gold").mkdir()
        (Path(self.tmp) / "gold" / "gold.jsonl").write_text("")
        (Path(self.tmp) / "queue.json").write_text(json.dumps({"arxiv:9999.00001@1": {"item": item(1), "attempts": 1, "last_error": "x"}}))
        with mock.patch.object(llm, "call_chain", fake_chain()), mock.patch.object(pipeline, "canary", lambda: {"ok": True}), \
                mock.patch.object(pipeline.sources, "fetch_all", side_effect=AssertionError("must not fetch")):
            r = pipeline.retry()
        self.assertEqual((r["processed"], r["queue_size"], r["auto_applied"]), (1, 0, 1))


class SourceText(unittest.TestCase):
    def test_result_stated_only_in_the_title_verifies(self):
        from qtd import stages
        from qtd.verify import verify
        it = {"title": "How to factor 2048 bit RSA integers in 8 hours using 20 million noisy qubits",
              "text": "We significantly reduce the cost of factoring."}
        ex = {"kind": "attack", "estimates": [{"quote": it["title"] + ".",  # the model copies the sentence with its period
                                               "fields": {"target": "2048 bit RSA", "physical_qubits": "20 million", "runtime": "8 hours"}}]}
        v = verify(ex, stages.source_text(it))
        self.assertTrue(v["ok_estimates"], v["estimates"])
        self.assertEqual(v["ok_estimates"][0]["values"]["physical_qubits"], 2e7)


class Dedupe(unittest.TestCase):
    def test_title_and_abstract_quotes_of_one_result_collapse(self):
        a = {"values": {"target": "rsa-2048", "physical_qubits": 1e6}}
        b = {"values": {"target": "rsa-2048", "physical_qubits": 1e6, "runtime": 168}}
        c = {"values": {"target": "ecdlp-256", "physical_qubits": 1e6}}
        d = {"values": {"target": "rsa-2048", "physical_qubits": 5e5}}
        self.assertEqual(pipeline.dedupe_estimates([a, b, c, d]), [b, c, d])
        self.assertEqual(len(pipeline.dedupe_estimates([a, dict(a)])), 1)  # exact duplicates keep one


class Chain(unittest.TestCase):
    def test_falls_through_and_reports_model(self):
        calls = []

        def fn(m):
            calls.append(m)
            if m == llm.CHAINS["primary"][0]:
                raise llm.LLMError("404 retired")
            return "ok"
        self.assertEqual(llm.call_chain("primary", fn), ("ok", llm.CHAINS["primary"][1]))
        with self.assertRaises(llm.LLMError):
            llm.call_chain("primary", lambda m: (_ for _ in ()).throw(llm.LLMError("down")))


if __name__ == "__main__":
    unittest.main()
