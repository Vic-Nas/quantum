import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from qtd import facts, llm, site  # noqa: E402

PAGE = "<html><title>Blog</title><body><p>OpenSSH now uses a hybrid ML-KEM key exchange by default. Signatures are classical.</p></body></html>"
PQ = {"id": "SSH", "kind": "pq", "topic": "SSH", "what": "key exchange", "url": "https://www.openssh.org/pq.html"}
FIG = {"id": "x", "kind": "figure", "group": "ecdlp-256", "label": "in old outputs", "ask": "How many?",
       "url": "https://chaincode.com/x.pdf"}
GOOD = {"answer": "protected", "quote": "OpenSSH now uses a hybrid ML-KEM key exchange by default."}


class Check(unittest.TestCase):
    PAGE = "openssh now uses a hybrid ml-kem key exchange by default. signatures are classical."

    def test_status_needs_a_verbatim_quote_and_a_known_word(self):
        self.assertEqual(facts.check(PQ, GOOD, self.PAGE), "protected")
        self.assertIsNone(facts.check(PQ, {**GOOD, "quote": "OpenSSH is invulnerable."}, self.PAGE))
        self.assertIsNone(facts.check(PQ, {**GOOD, "answer": "excellent"}, self.PAGE))
        self.assertIsNone(facts.check(PQ, {**GOOD, "answer": "unknown"}, self.PAGE))

    def test_figure_must_appear_in_its_quote(self):
        page = "about 1.7 million btc sit in p2pk outputs."
        ok = {"answer": "1.7 million BTC", "quote": "About 1.7 million BTC sit in P2PK outputs."}
        self.assertEqual(facts.check(FIG, ok, page), "1.7 million BTC")
        self.assertIsNone(facts.check(FIG, {**ok, "answer": "2.5 million BTC"}, page))


class Run(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.d = Path(self.tmp.name)
        patch = mock.patch.object(facts, "DATA", self.d)
        patch.start()
        self.addCleanup(patch.stop)
        (self.d / "facts_sources.json").write_text(json.dumps([PQ]))

    def go(self, answers):
        outs = iter(answers)
        with mock.patch.object(facts.http, "get", return_value=PAGE.encode()), \
                mock.patch.object(facts.llm, "generate", side_effect=lambda *a, **k: next(outs)):
            return facts.run()

    def stored(self):
        return json.loads((self.d / "facts.json").read_text())

    def test_two_agreeing_models_store_the_fact(self):
        out = self.go([GOOD, GOOD])
        self.assertEqual(out["applied"], 1)
        self.assertEqual(self.stored()["SSH"]["answer"], "protected")
        self.assertEqual(self.stored()["SSH"]["url"], PQ["url"])

    def test_disagreement_stores_nothing(self):
        out = self.go([GOOD, {**GOOD, "answer": "partial"}])
        self.assertEqual(out["unconfirmed"], 1)
        self.assertEqual(self.stored(), {})

    def test_model_outage_leaves_page_for_the_next_run(self):
        with mock.patch.object(facts.http, "get", return_value=PAGE.encode()), \
                mock.patch.object(facts.llm, "generate", side_effect=llm.LLMError("down")):
            out = facts.run()
        self.assertEqual(out["unavailable"], 1)
        self.assertEqual(json.loads((self.d / "facts_seen.json").read_text()), {})

    def test_manual_lines_are_never_overwritten(self):
        (self.d / "facts.json").write_text(json.dumps({"SSH": {"pq_status": "none", "manual": True}}))
        out = self.go([])
        self.assertEqual(out["changed"], 0)
        self.assertEqual(self.stored()["SSH"]["pq_status"], "none")

    def test_a_hand_edit_is_safe_without_any_flag(self):
        edit = {"kind": "pq", "topic": "SSH", "answer": "none", "note": "my edit"}
        (self.d / "facts.json").write_text(json.dumps({"SSH": edit}))
        out = self.go([])
        self.assertEqual(out["changed"], 0)
        self.assertEqual(self.stored()["SSH"], edit)

    def test_seeded_and_machine_entries_are_replaced(self):
        (self.d / "facts.json").write_text(json.dumps({"SSH": {"answer": "none", "seed": True}}))
        self.go([GOOD, GOOD])
        self.assertEqual(self.stored()["SSH"]["answer"], "protected")
        self.assertNotIn("seed", self.stored()["SSH"])

    def test_unchanged_page_is_not_asked_again(self):
        self.go([GOOD, GOOD])
        out = self.go([])
        self.assertEqual(out["changed"], 0)

    def test_services_without_a_source_are_listed_for_a_person(self):
        out = self.go([GOOD, GOOD])
        self.assertIn("WhatsApp", out["needs_a_person"])
        self.assertNotIn("SSH", out["needs_a_person"])


class Render(unittest.TestCase):
    def test_service_card_uses_fact_status_and_quote(self):
        crows = [{"slug": "bitcoin", "year": 2031, "safe": False}]
        fact = {"answer": "none", "quote": "No protection here.", "url": "https://openssh.org/pq.html", "checked": "2026-11-09"}
        html = site.services_html(crows, {}, {"SSH": fact})
        self.assertIn("No PQ protection yet", html)
        self.assertIn("No protection here.", html)
        self.assertIn("openssh.org/pq.html", html)

    def test_person_line_sets_status_and_note(self):
        html = site.services_html([], {}, {"WhatsApp": {"pq_status": "partial", "note": "Meta said so.", "manual": True}})
        self.assertIn("Partly protected", html)
        self.assertIn("Meta said so.", html)


if __name__ == "__main__":
    unittest.main()
