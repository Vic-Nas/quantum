import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class Css(unittest.TestCase):
    def test_sticky_bar_is_opaque(self):
        css = (ROOT / "web" / "css" / "base.css").read_text()
        self.assertIn("background:var(--paper);border-bottom:1px solid var(--rule)", css)
        self.assertNotIn("backdrop-filter", css)


if __name__ == "__main__":
    unittest.main()
