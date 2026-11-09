import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from qtd import llm  # noqa: E402


class ParseJson(unittest.TestCase):
    def test_plain_and_fenced(self):
        self.assertEqual(llm.parse_json('{"a": 1}'), {"a": 1})
        self.assertEqual(llm.parse_json('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(llm.parse_json(' { "answer": "ok" } ```'), {"answer": "ok"})

    def test_garbage(self):
        with self.assertRaises(ValueError):
            llm.parse_json("no json here")


class Timeouts(unittest.TestCase):
    def test_read_timeout_is_a_model_failure_not_a_crash(self):
        import os
        import tempfile
        from unittest import mock
        llm.CACHE = Path(tempfile.mkdtemp())
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "x"}), \
                mock.patch.object(llm.urllib.request, "urlopen", side_effect=TimeoutError("read timed out")), \
                mock.patch.object(llm.time, "sleep", lambda s: None):
            with self.assertRaises(llm.LLMError):
                llm.generate("gemini-3.5-flash-lite", "p", {"type": "OBJECT"})


class Budget(unittest.TestCase):
    def test_cap(self):
        import tempfile
        llm.CACHE = Path(tempfile.mkdtemp())
        cap = int(llm.DEFAULT_LIMIT[1] * llm.BUDGET_FRACTION)
        for _ in range(cap):
            llm._spend("some-5rpm-model")
        with self.assertRaises(llm.LLMError):
            llm._spend("some-5rpm-model")


if __name__ == "__main__":
    unittest.main()
