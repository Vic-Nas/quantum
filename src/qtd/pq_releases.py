"""Check GitHub releases of tracked projects for post-quantum keywords.

Writes data/pq_status.json with per-service overrides that the site builder
merges on top of the hardcoded SERVICES defaults in present.py.

Uses `gh api` (available in GitHub Actions) or falls back to urllib.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

DATA = Path("data")

# (service name matching SERVICES in present.py, list of GitHub owner/repo to check)
TRACKED = [
    ("Signal", ["signalapp/libsignal"]),
    ("SSH", ["openssh/openssh-portable"]),
    ("WireGuard", ["WireGuard/wireguard-linux-compat", "WireGuard/wireguard-tools"]),
    ("Bitcoin", ["bitcoin/bitcoin"]),
    ("Ethereum", ["ethereum/go-ethereum"]),
    ("Bitwarden", ["bitwarden/clients"]),
    ("OpenVPN", ["OpenVPN/openvpn"]),
]

# Deduplicated repo list and reverse map
REPOS: list[str] = []
_REPO_TO_SERVICES: dict[str, list[str]] = {}
for _name, _repos in TRACKED:
    for _r in _repos:
        if _r not in REPOS:
            REPOS.append(_r)
        _REPO_TO_SERVICES.setdefault(_r, []).append(_name)

PQ_KEYWORDS = re.compile(
    r"post.?quantum|pq(?:xdh|3|c)\b|ml.?kem|ml.?dsa|kyber|dilithium|"
    r"classic.?mceliece|sphincs|slh.?dsa|x25519.?ml.?kem|sntrup761|streamlined.?ntru|quantum.?(?:resistan|safe)",
    re.IGNORECASE,
)

_HAS_GH = shutil.which("gh") is not None


def _fetch_releases(repo: str) -> list:
    """Fetch up to 10 recent releases for a repo. Tries gh CLI first, then urllib."""
    if _HAS_GH:
        try:
            r = subprocess.run(
                ["gh", "api", f"repos/{repo}/releases", "--paginate", "-q", ".[:10]"],
                capture_output=True, timeout=30, text=True,
            )
            if r.returncode == 0 and r.stdout.strip():
                return json.loads(r.stdout)
        except Exception:
            pass
    # Fallback to direct HTTP (works when not behind a restrictive proxy)
    try:
        from . import http
        raw = http.get(
            f"https://api.github.com/repos/{repo}/releases?per_page=10",
            headers={"Accept": "application/vnd.github+json"},
            timeout=10, retries=1,
        )
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def check_releases() -> dict:
    """Check recent releases for PQ keywords. Returns {service_name: {found, release, ...}}."""
    hits: dict[str, dict] = {}
    for repo in REPOS:
        releases = _fetch_releases(repo)
        for rel in releases:
            name = rel.get("name") or rel.get("tag_name") or ""
            body = rel.get("body") or ""
            tag = rel.get("tag_name") or ""
            text = f"{name} {tag} {body}"
            m = PQ_KEYWORDS.search(text)
            if m:
                for svc in _REPO_TO_SERVICES.get(repo, []):
                    if svc not in hits:
                        hits[svc] = {
                            "found": True,
                            "release": tag,
                            "repo": repo,
                            "keyword": m.group(),
                            "published": (rel.get("published_at") or "")[:10],
                        }
                break
    return hits


def _infer_status(hit: dict) -> str:
    kw = hit.get("keyword", "").lower()
    if any(w in kw for w in ("pqxdh", "pq3", "ml-kem", "mlkem", "hybrid")):
        return "migrating"
    return "partial"


def run(dry: bool = False) -> dict:
    """Check releases and write data/pq_status.json. Returns summary."""
    hits = check_releases()
    path = DATA / "pq_status.json"
    existing = json.loads(path.read_text()) if path.exists() else {}

    updated = 0
    for svc, hit in hits.items():
        old = existing.get(svc, {})
        if old.get("manual"):
            continue
        new_status = _infer_status(hit)
        if old.get("pq_status") != new_status or old.get("release") != hit["release"]:
            existing[svc] = {
                "pq_status": new_status,
                "release": hit["release"],
                "repo": hit["repo"],
                "keyword": hit["keyword"],
                "published": hit["published"],
            }
            updated += 1

    if not dry:
        path.write_text(json.dumps(existing, indent=1) + "\n")

    return {"checked_repos": len(REPOS), "hits": len(hits), "updated": updated}
