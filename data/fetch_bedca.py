"""Download the BEDCA composition of the foods that have a `bedca_id` in food_targets.csv.

Uses the official public XML query interface of bedca.net, one request at a time with a pause
between them, and caches each answer in data/raw/bedca/<id>.xml (not in git). Values are kept
exactly as BEDCA returns them.

BEDCA conditions: personal, educational or non-commercial use, with attribution; values may not
be modified; reproduction in electronic format requires AESAN's express authorisation (requested
on 2026-10-12, used meanwhile as educational use while the repository is private; ADR-25).

Run: uv run --group data python data/fetch_bedca.py
"""

from __future__ import annotations

import csv
import time
import urllib.request
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent
CACHE_DIR = DATA_DIR / "raw" / "bedca"
URL = "https://www.bedca.net/bdpub/procquery.php"
PAUSE_S = 2.5
FIELDS = ["f_id", "f_ori_name", "f_eng_name", "edible_portion", "f_origen", "c_id", "c_ori_name", "c_eng_name"]
FIELDS += ["eur_name", "best_location", "v_unit", "moex", "value_type"]


def detail_query(food_id: str) -> str:
    selection = "".join(f'<atribute name="{name}"/>' for name in FIELDS)
    return (
        '<?xml version="1.0" encoding="utf-8"?><foodquery><type level="2"/>'
        f"<selection>{selection}</selection>"
        '<condition><cond1><atribute1 name="f_id"/></cond1><relation type="EQUAL"/>'
        f"<cond3>{int(food_id)}</cond3></condition>"
        '<condition><cond1><atribute1 name="publico"/></cond1><relation type="EQUAL"/><cond3>1</cond3></condition>'
        '<order ordtype="ASC"><atribute3 name="componentgroup_id"/></order></foodquery>'
    )


def fetch(food_id: str) -> str:
    request = urllib.request.Request(
        URL,
        data=detail_query(food_id).encode(),
        headers={"Content-Type": "text/xml", "User-Agent": "mojo-picon food table build (educational project)"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        text = response.read().decode("utf-8")
    if text.startswith("error: ") or "<foodresponse>" not in text:
        raise RuntimeError(f"BEDCA food {food_id}: unexpected answer {text[:120]!r}")
    return text


def main() -> int:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with (DATA_DIR / "food_targets.csv").open(encoding="utf-8") as f:
        ids = sorted({row["bedca_id"] for row in csv.DictReader(f) if row.get("bedca_id")})
    for i, food_id in enumerate(ids):
        path = CACHE_DIR / f"{food_id}.xml"
        if path.exists():
            print(f"{food_id}: cached")
            continue
        if i:
            time.sleep(PAUSE_S)
        path.write_text(fetch(food_id), encoding="utf-8")
        print(f"{food_id}: downloaded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
