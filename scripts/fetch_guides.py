"""Download the guideline corpus listed in data/guides.json into data/raw/guides/ (git-ignored).

Only public or open-access documents; each one carries its licence in the manifest (specs: RAG).
Already downloaded files are kept unless --force. Prints the SHA-256 of each file so a rebuilt
index can be traced to the exact documents.

    uv run python scripts/fetch_guides.py [--force]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "guides.json"
RAW = ROOT / "data" / "raw" / "guides"
EXTENSIONS = {"pdf": ".pdf", "html": ".html", "jats": ".xml"}
USER_AGENT = "mojo-picon/0.1 (master's project; guideline corpus)"


def load_manifest(path: Path = MANIFEST) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def raw_path(guide: dict, raw: Path = RAW) -> Path:
    return raw / f"{guide['id']}{EXTENSIONS[guide['format']]}"


def fetch(guide: dict, force: bool = False) -> Path:
    path = raw_path(guide)
    if path.exists() and not force:
        return path
    request = urllib.request.Request(guide["url"], headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        data = response.read()
    if guide["format"] == "pdf" and not data.startswith(b"%PDF"):
        raise ValueError(f"{guide['id']}: not a PDF ({guide['url']})")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="download again even if the file exists")
    args = parser.parse_args()
    for guide in load_manifest():
        path = fetch(guide, args.force)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        print(f"{guide['id']:24} {path.stat().st_size / 1e6:6.2f} MB  sha256:{digest}  {guide['license']}")


if __name__ == "__main__":
    main()
