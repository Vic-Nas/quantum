"""Tiny HTTP helper with retry. Honors the environment proxy and CA bundle."""
import time
import urllib.request


def get(url: str, timeout: int = 30, retries: int = 3, headers: dict | None = None) -> bytes:
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "qtd-pipeline", **(headers or {})})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 ** i)
    raise RuntimeError(f"GET failed: {url}: {last}")
