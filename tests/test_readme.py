import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from qtd import readme  # noqa: E402


class Readme(unittest.TestCase):
    def test_adds_replaces_and_is_idempotent(self):
        body = "Some text.\n"
        a = readme.update(body, "https://a.example/")
        self.assertIn('<a href="https://a.example/">', a)
        self.assertIn("Quantum threat tracker", a)
        self.assertIn("web/favicon.svg", a)
        self.assertEqual(readme.update(a, "https://a.example/"), a)  # idempotent
        b = readme.update(a, "https://b.example/")
        self.assertNotIn("a.example", b)
        self.assertIn("https://b.example/", b)
        self.assertTrue(b.endswith("Some text.\n"))
        self.assertEqual(b.count(readme.START), 1)

    def test_url_is_only_ever_a_link_target_never_visible_text(self):
        out = readme.update("x", 'https://e.example/?a="b"')
        visible = out.split(">", 1)[1]  # everything after the opening marker comment
        self.assertNotIn(">https://", out)
        self.assertIn("&quot;", out)  # attribute is escaped
        self.assertIn("Quantum threat tracker</a>", visible)


if __name__ == "__main__":
    unittest.main()
