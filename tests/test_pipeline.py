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
        model = {"primary": "gemini-3.5-flash-lite", "secondary": "gemini-3.5-flash-lite" if same_family else "gemini-3.1-flash-lite",
                 "escalation": "gemini-3.8-flash"}[role]
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
    """The frequent run must stay cheap: it may only repeat work that failed, and never do a full run's work."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        pipeline.DATA = Path(self.tmp)
        (Path(self.tmp) / "gold").mkdir()
        (Path(self.tmp) / "gold" / "gold.jsonl").write_text("")
        llm.set_run_budget(None)

    def tearDown(self):
        llm.set_run_budget(None)

    def write(self, name, data):
        (Path(self.tmp) / name).write_text(json.dumps(data))

    def run_retry(self):
        calls = {"run": [], "hw": []}

        def fake_run(**kw):
            calls["run"].append(kw)
            return {"processed": 0}

        def fake_hw(**kw):
            calls["hw"].append(kw)
            return {}
        with mock.patch.object(pipeline, "run", fake_run), mock.patch.object(pipeline, "run_hardware", fake_hw), \
                mock.patch.object(pipeline.sources, "fetch_all", side_effect=AssertionError("must never fetch papers")), \
                mock.patch.object(pipeline.sources, "fetch_pages", side_effect=AssertionError("must never fetch pages unprompted")), \
                mock.patch.object(llm, "call_chain", side_effect=AssertionError("no model call without something to retry")):
            return pipeline.retry(), calls

    def test_idle_when_nothing_failed(self):
        out, calls = self.run_retry()
        self.assertEqual((out, calls), ({"idle": True}, {"run": [], "hw": []}))

    def test_a_stale_or_error_ridden_status_does_not_turn_it_into_a_full_run(self):
        self.write("status.json", {"run_at": "2020-01-01T00:00:00+00:00", "source_errors": {"arxiv": "429"}})
        out, calls = self.run_retry()
        self.assertEqual((out, calls), ({"idle": True}, {"run": [], "hw": []}))  # fetch problems wait for the daily run

    def test_queue_is_capped_never_fetches_and_gets_a_call_budget(self):
        self.write("queue.json", {f"arxiv:9.{n}@1": {"item": item(n), "attempts": 1, "last_error": "x"} for n in range(1, 6)})
        out, calls = self.run_retry()
        self.assertEqual(calls["run"], [{"items": [], "fulltext": True, "limit": pipeline.MAX_RETRY_PAPERS}])
        self.assertEqual(calls["hw"], [])
        self.assertEqual(llm._run_budget, pipeline.RETRY_CALL_BUDGET)

    def test_only_failed_vendor_pages_are_retried(self):
        pend = [{"id": "page:x/y", "url": "https://ionq.com/roadmap", "actor": "IonQ"}]
        self.write("hw_pending.json", pend)
        out, calls = self.run_retry()
        self.assertEqual((calls["run"], calls["hw"]), ([], [{"only": pend}]))

    def test_real_requests_are_capped_but_cache_hits_are_free(self):
        llm.CACHE = Path(self.tmp) / "cache"
        llm.set_run_budget(3)
        for _ in range(3):
            llm._spend("gemini-3.5-flash-lite")
        with self.assertRaises(llm.LLMError):
            llm._spend("gemini-3.5-flash-lite")
        # a cached answer needs no request, so it is served even when the budget is spent
        import hashlib
        key = hashlib.sha256(json.dumps(["m", "p", {}], sort_keys=True).encode()).hexdigest()
        (llm.CACHE / f"{key}.json").write_text('{"a": 1}')
        self.assertEqual(llm.generate("m", "p", {}), {"a": 1})

    def test_the_queue_really_is_processed_end_to_end_within_the_cap(self):
        self.write("queue.json", {f"arxiv:9999.{n:05d}@1": {"item": item(n), "attempts": 1, "last_error": "x"} for n in range(1, 5)})
        with mock.patch.object(llm, "call_chain", fake_chain()), mock.patch.object(pipeline, "canary", lambda: {"ok": True}), \
                mock.patch.object(pipeline.sources, "fetch_all", side_effect=AssertionError("must not fetch")), \
                mock.patch.object(pipeline.sources, "fetch_fulltext", return_value=""):
            out = pipeline.retry()
        self.assertEqual(out["papers"]["processed"], pipeline.MAX_RETRY_PAPERS)  # 4 queued, only 2 taken
        self.assertEqual(out["papers"]["queue_size"], 2)


class Seed(unittest.TestCase):
    def test_seed_rebuilds_papers_but_leaves_hardware_rows_alone(self):
        tmp = tempfile.mkdtemp()
        pipeline.DATA = Path(tmp)
        (Path(tmp) / "seed_papers.json").write_text(json.dumps({"ids": ["1.1"]}))
        (Path(tmp) / "hardware.json").write_text(json.dumps([{"id": "hw#0", "actor": "IonQ"}]))
        (Path(tmp) / "attacks.json").write_text(json.dumps([{"id": "old#0"}]))
        (Path(tmp) / "gold").mkdir()
        (Path(tmp) / "gold" / "gold.jsonl").write_text("")
        with mock.patch.object(pipeline.sources, "fetch_arxiv_ids", return_value=[item()]), \
                mock.patch.object(llm, "call_chain", fake_chain()), mock.patch.object(pipeline.sources, "fetch_fulltext", return_value=""):
            pipeline.seed()
        self.assertEqual(json.loads((Path(tmp) / "hardware.json").read_text()), [{"id": "hw#0", "actor": "IonQ"}])
        self.assertNotIn("old#0", (Path(tmp) / "attacks.json").read_text())


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


class TieBreak(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        pipeline.DATA = Path(self.tmp)
        (Path(self.tmp) / "gold").mkdir()
        (Path(self.tmp) / "gold" / "gold.jsonl").write_text("")

    def chain(self, second_ok, third_ok):
        base = fake_chain()
        empty = {"kind": "attack", "estimates": []}

        def fn(role, f, exclude=None):
            if role == "secondary" and not second_ok:
                return empty, "gemini-3.1-flash-lite"
            if role == "escalation":
                return (base("primary", f)[0] if third_ok else empty), "gemini-3.8-flash"
            return base(role, f, exclude)
        return fn

    def test_two_of_three_confirm(self):
        with mock.patch.object(llm, "call_chain", self.chain(second_ok=False, third_ok=True)), \
                mock.patch.object(pipeline, "canary", lambda: {"ok": True}):
            r = pipeline.run(items=[item()])
        self.assertEqual((r["counts"]["A"], r["auto_applied"]), (1, 1))

    def test_one_of_three_is_not_enough(self):
        with mock.patch.object(llm, "call_chain", self.chain(second_ok=False, third_ok=False)), \
                mock.patch.object(pipeline, "canary", lambda: {"ok": True}):
            r = pipeline.run(items=[item()])
        self.assertEqual((r["counts"]["A"], r["counts"]["B"], r["auto_applied"]), (0, 1, 0))

    def test_unavailable_tiebreak_leaves_it_unconfirmed(self):
        def fn(role, f, exclude=None):
            if role == "escalation":
                raise llm.LLMError("quota")
            if role == "secondary":
                return {"kind": "attack", "estimates": []}, "gemini-3.1-flash-lite"
            return fake_chain()(role, f, exclude)
        with mock.patch.object(llm, "call_chain", fn):
            r = pipeline.run(items=[item()])
        self.assertEqual((r["counts"]["B"], r["auto_applied"]), (1, 0))


class Dedupe(unittest.TestCase):
    def test_title_and_abstract_quotes_of_one_result_collapse(self):
        a = {"values": {"target": "rsa-2048", "physical_qubits": 1e6}}
        b = {"values": {"target": "rsa-2048", "physical_qubits": 1e6, "runtime": 168}}
        c = {"values": {"target": "ecdlp-256", "physical_qubits": 1e6}}
        d = {"values": {"target": "rsa-2048", "physical_qubits": 5e5}}
        self.assertEqual(pipeline.dedupe_estimates([a, b, c, d]), [b, c, d])
        self.assertEqual(len(pipeline.dedupe_estimates([a, dict(a)])), 1)  # exact duplicates keep one
        failed_rich = dict(b, tier="drop")  # a richer estimate that failed verification must not erase a verified one
        self.assertEqual(pipeline.dedupe_estimates([a, failed_rich]), [a, failed_rich])


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


class Backfill(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        pipeline.DATA = self.tmp
        (self.tmp / "gold").mkdir()
        (self.tmp / "gold" / "gold.jsonl").write_text("")
        (self.tmp / "seed_papers.json").write_text(json.dumps({"ids": ["1111.00001", "1111.00002", "1111.00003"]}))

    def test_takes_the_next_unread_ids_and_marks_unknown_ones_read(self):
        got = [{**item(1), "id": "arxiv:1111.00001", "version": "seed", "history": True}]
        seen = set()
        with mock.patch.object(pipeline.sources, "backfill", return_value=got) as bf:
            items, err = pipeline._backfill(seen, 2)
        bf.assert_called_once_with(["1111.00001", "1111.00002"])
        self.assertEqual(items, got)
        self.assertEqual(seen, {"arxiv:1111.00002@seed"})  # arXiv did not know it: never blocks the list
        self.assertEqual(err, {})

    def test_an_arxiv_outage_is_reported_not_fatal(self):
        with mock.patch.object(pipeline.sources, "backfill", side_effect=RuntimeError("GET failed")):
            items, err = pipeline._backfill(set(), 4)
        self.assertEqual(items, [])
        self.assertIn("backfill", err)

    def test_nothing_left_costs_nothing(self):
        seen = {f"arxiv:1111.0000{n}@seed" for n in (1, 2, 3)}
        with mock.patch.object(pipeline.sources, "backfill") as bf:
            self.assertEqual(pipeline._backfill(seen, 4), ([], {}))
        bf.assert_not_called()

    def test_an_older_paper_is_added_as_history_but_a_new_one_must_beat_the_best(self):
        (self.tmp / "attacks.json").write_text(json.dumps([{"id": "arxiv:1.0#0", "target": "rsa-2048", "physical_qubits": 1000.0}]))
        old = {**item(2), "history": True}
        new = item(3)
        with mock.patch.object(llm, "call_chain", fake_chain()), mock.patch.object(pipeline, "canary", lambda: {"ok": True}):
            r = pipeline.run(items=[old, new])
        self.assertEqual(r["counts"]["A"], 1)  # the history paper; the other is not cheaper than 1,000 qubits
        ids = [x["id"] for x in json.loads((self.tmp / "attacks.json").read_text())]
        self.assertIn("arxiv:9999.00002#0", ids)
        self.assertNotIn("arxiv:9999.00003#0", ids)


if __name__ == "__main__":
    unittest.main()
