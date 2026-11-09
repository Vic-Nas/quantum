import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from qtd import regex_extract, router, sources  # noqa: E402
from qtd.prefilter import prefilter  # noqa: E402
from qtd.textutil import canonical_target, numbers_in, parse_hours  # noqa: E402
from qtd.verify import agree, verify  # noqa: E402

ABS = ("We show that 2048-bit RSA integers can be factored in less than a week using fewer than "
       "a million noisy qubits. The algorithm needs 1,400 logical qubits and 6.5 billion Toffoli gates.")


class TextUtil(unittest.TestCase):
    def test_numbers(self):
        self.assertIn(1e6, numbers_in("fewer than a million noisy qubits"))
        self.assertIn(1400.0, numbers_in("1,400 logical qubits"))
        self.assertIn(6.5e9, numbers_in("6.5 billion Toffoli"))
        self.assertIn(5e7, numbers_in("50 million"))
        self.assertEqual(numbers_in("a quantum computer"), [])

    def test_hours(self):
        self.assertEqual(parse_hours("in less than a week"), 168)
        self.assertEqual(parse_hours("about 8 days"), 192)
        self.assertEqual(parse_hours("in 9 h with 126133 cat qubits"), 9)
        self.assertEqual(parse_hours("takes 30 min"), 0.5)
        self.assertEqual(parse_hours("26 d"), 624)
        self.assertEqual(parse_hours("2 months"), 1460)
        self.assertIsNone(parse_hours("with 5 hardware qubits and 2 dozen"))

    def test_targets(self):
        self.assertEqual(canonical_target("factor 2048-bit RSA integers"), "rsa-2048")
        self.assertEqual(canonical_target("secp256k1 keys"), "ecdlp-256")
        self.assertIsNone(canonical_target("lattice crypto"))


class Verify(unittest.TestCase):
    def test_regex_roundtrip_verifies(self):
        ex = regex_extract.extract(ABS)
        v = verify(ex, ABS)
        self.assertTrue(v["ok_estimates"], v["estimates"])
        vals = v["ok_estimates"][0]["values"]
        self.assertEqual(vals["target"], "rsa-2048")
        self.assertEqual(vals["physical_qubits"], 1e6)

    def _est(self, quote, **fields):
        return {"kind": "attack", "estimates": [{"quote": quote, "fields": fields}]}

    def test_fabricated_quote_rejected(self):
        ex = self._est("RSA-2048 falls in a day.", target="RSA-2048", logical_qubits="10")
        self.assertFalse(verify(ex, ABS)["ok_estimates"])

    def test_wrong_number_rejected(self):
        q = "We show that 2048-bit RSA integers can be factored in less than a week using fewer than a million noisy qubits."
        ex = self._est(q, target="RSA-2048", physical_qubits="2 million")
        self.assertFalse(verify(ex, ABS)["ok_estimates"])
        ex = self._est(q, target="RSA-2048", physical_qubits="a million")
        self.assertTrue(verify(ex, ABS)["ok_estimates"])

    def test_bounds(self):
        t = "We factor RSA-2048 with 5 logical qubits."
        self.assertTrue(verify(self._est(t, target="RSA-2048", logical_qubits="5"), t)["ok_estimates"])
        t2 = "We factor RSA-2048 with 900000000000 logical qubits."
        self.assertFalse(verify(self._est(t2, target="RSA-2048", logical_qubits="900000000000"), t2)["ok_estimates"])

    def test_target_must_be_in_quote(self):
        t = "We need 5 logical qubits. RSA-2048 is hard."
        self.assertFalse(verify(self._est("We need 5 logical qubits.", target="RSA-2048",
                                          logical_qubits="5"), t)["ok_estimates"])

    def test_duration_and_notation(self):
        t = "Factoring RSA-2048 requires about 23 000 cat qubits and 3.14 days, or 381k qubits and $40\\cdot 10^6$ Toffoli."
        v = verify(self._est(t, target="RSA-2048", physical_qubits="23 000", runtime="3.14 days",
                             toffoli_or_t_count="40\\cdot 10^6"), t)
        self.assertTrue(v["ok_estimates"], v["estimates"])
        self.assertAlmostEqual(v["ok_estimates"][0]["values"]["runtime"], 75.36)
        self.assertIn(381000.0, numbers_in(t))

    def test_latex_stripped_quote_still_verifies(self):
        src = "We solve ECDLP on $\\mathtt{secp256k1}$ using about $1450$ qubits and $40\\cdot 10^6$ Toffoli gates."
        q = "We solve ECDLP on secp256k1 using about 1450 qubits and 40*10^6 Toffoli gates."
        v = verify(self._est(q, target="secp256k1", logical_qubits="1450", toffoli_or_t_count="40*10^6"), src)
        self.assertTrue(v["ok_estimates"], v["estimates"])
        self.assertEqual(v["ok_estimates"][0]["values"]["toffoli_or_t_count"], 4e7)
        # markup stripping must not let invented text through
        bad = self._est("We solve ECDLP on secp256k1 using about 9 qubits.", target="secp256k1", logical_qubits="9")
        self.assertFalse(verify(bad, src)["ok_estimates"])

    def test_not_allowlisted(self):
        self.assertFalse(verify(regex_extract.extract(ABS), ABS, allowlisted=False)["ok_estimates"])

    def test_agree(self):
        self.assertTrue(agree({"target": "x", "a": 1.0}, {"target": "x", "a": 1.0}))
        self.assertFalse(agree({"target": "x", "a": 1.0}, {"target": "x", "a": 2.0}))
        self.assertTrue(agree({"target": "x", "q": 22593.0, "r": 75.36}, {"target": "x", "q": 23000.0, "r": 75.36}))
        self.assertFalse(agree({"target": "x", "q": 22593.0}, {"target": "x", "q": 27000.0}))  # 20% apart is a different result
        self.assertFalse(agree({"a": 1.0}, {"a": 1.0}))
        self.assertFalse(agree({"target": "x", "a": 1.0}, {"target": "x", "b": 2.0}))
        self.assertFalse(agree({"target": "x"}, {"target": "x"}))


class Router(unittest.TestCase):
    rows = [{"target": "rsa-2048", "physical_qubits": 2e7, "logical_qubits": 6000}]

    def test_frontier(self):
        self.assertTrue(router.is_frontier({"target": "rsa-2048", "physical_qubits": 1e6}, self.rows))
        self.assertFalse(router.is_frontier({"target": "rsa-2048", "physical_qubits": 3e7}, self.rows))
        self.assertTrue(router.is_frontier({"target": "ecdlp-256"}, self.rows))

    def test_route(self):
        v = {"target": "rsa-2048", "physical_qubits": 1e6}
        self.assertEqual(router.route("attack", True, v, True, self.rows)[0], "A")
        self.assertEqual(router.route("attack", True, v, False, self.rows)[0], "B")
        self.assertEqual(router.route("attack", False, v, True, self.rows)[0], "drop")
        no_qubits = {"target": "ecdlp-256", "toffoli_or_t_count": 5e7}
        self.assertEqual(router.route("attack", True, no_qubits, True, self.rows)[0], "drop")  # nothing to chart
        self.assertEqual(router.route("attack", True, {"target": "rsa-2048", "physical_qubits": 3e7},
                                      True, self.rows)[0], "B")


class Sources(unittest.TestCase):
    def test_allowlist(self):
        self.assertTrue(sources.is_allowlisted("https://arxiv.org/abs/2505.15917"))
        self.assertFalse(sources.is_allowlisted("https://evil.example.com/arxiv.org"))

    def test_parse_arxiv(self):
        xml = (b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/abs/2505.15917v2</id>'
               b'<title>T\n x</title><summary> S </summary><published>2025-05-21T00:00:00Z</published>'
               b'<updated>2025-06-01T00:00:00Z</updated></entry></feed>')
        it = sources.parse_arxiv(xml)[0]
        self.assertEqual((it["id"], it["version"], it["title"]), ("arxiv:2505.15917", "2", "T x"))

    def test_prefilter(self):
        self.assertTrue(prefilter({"title": "RSA", "text": ABS})["keep"])
        self.assertFalse(prefilter({"title": "Lattices", "text": "A new lattice scheme."})["keep"])


if __name__ == "__main__":
    unittest.main()
