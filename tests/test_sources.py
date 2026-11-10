import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from qtd import sources  # noqa: E402


class ArxivPacing(unittest.TestCase):
    def test_search_queries_are_spaced(self):
        queries = ["au:first", "au:second", "au:third"]
        with mock.patch.object(sources.http, "get", return_value=b"<feed />"), \
                mock.patch.object(sources.time, "sleep") as sleep:
            sources.fetch_arxiv(queries=queries)
        sleep.assert_has_calls([mock.call(sources.http.ARXIV_MIN_INTERVAL),
                                mock.call(sources.http.ARXIV_MIN_INTERVAL)])
        self.assertEqual(sleep.call_count, 2)


if __name__ == "__main__":
    unittest.main()
