import io
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from qtd import http  # noqa: E402


class Retry(unittest.TestCase):
    def test_rate_limit_waits_long_then_succeeds(self):
        calls, sleeps = [], []

        class R(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): return False

        def fake_open(req, timeout=0):
            calls.append(1)
            if len(calls) < 3:
                raise urllib.error.HTTPError(req.full_url, 429, "Too Many", {}, io.BytesIO(b""))
            return R(b"ok")
        with mock.patch.object(http.urllib.request, "urlopen", fake_open), mock.patch.object(http.time, "sleep", sleeps.append):
            self.assertEqual(http.get("https://x.example/"), b"ok")
        self.assertEqual(sleeps, [30, 60])  # long waits for 429

    def test_gives_up_with_clear_error(self):
        with mock.patch.object(http.urllib.request, "urlopen", side_effect=TimeoutError("t")), \
                mock.patch.object(http.time, "sleep", lambda s: None):
            with self.assertRaises(RuntimeError):
                http.get("https://x.example/", retries=2)


if __name__ == "__main__":
    unittest.main()
