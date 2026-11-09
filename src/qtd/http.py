"""Tiny HTTP helper with retry. Honors the environment proxy and CA bundle."""
import time
import urllib.error
import urllib.request


def get(url: str, timeout: int = 30, retries: int = 4, headers: dict | None = None) -> bytes:
    """GET with retries. Rate limits (429) and 503 wait much longer than ordinary errors."""
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "qtd-pipeline", **(headers or {})})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last = e
            wait = 30 * (i + 1) if e.code in (429, 503) else 2 ** i
        except Exception as e:  # noqa: BLE001
            last = e
            wait = 2 ** i
        if i < retries - 1:
            time.sleep(wait)
    raise RuntimeError(f"GET failed: {url}: {last}")
