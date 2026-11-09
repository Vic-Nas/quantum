"""Keep the README header in step with the public page address (QTD_SITE_URL), shown as a title, never a bare link."""
import html
import sys
from pathlib import Path

START, END = "<!-- site:start -->", "<!-- site:end -->"


def header(url: str) -> str:
    return (f'{START}\n<h1><a href="{html.escape(url, quote=True)}"><img src="web/favicon.svg" alt="" width="30" height="30" '
            f'align="absmiddle"> Quantum threat tracker</a></h1>\n{END}')


def update(text: str, url: str) -> str:
    """Replace the marked header block (or add it at the top if missing). Idempotent."""
    block = header(url)
    if START in text and END in text:
        before, rest = text.split(START, 1)
        _, after = rest.split(END, 1)
        return before + block + after
    return block + "\n\n" + text.lstrip("\n")


if __name__ == "__main__":
    from .site import base_url
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "README.md")
    old = path.read_text() if path.exists() else ""
    new = update(old, base_url())
    if new != old:
        path.write_text(new)
        print("README header updated")
