"""The container image must carry every data file the app reads at runtime.

Found in production on 2026-10-19: the household measures were not copied into the image, so
search_food and get_nutrients failed there while every test and evaluation (outside the image) passed.
"""

import re
from pathlib import Path

from mojo_picon.tools import energy, foods, measures, recipes

ROOT = Path(__file__).resolve().parents[2]
# 22 Oct: the recipe library was missing too; log_meal, get_nutrients and check_allergens load it
RUNTIME_DATA = [foods.DEFAULT_FOODS, energy.DEFAULT_MET_TABLE, measures.DEFAULT_MEASURES, measures.DEFAULT_DEFINITIONS,
                recipes.DEFAULT_RECIPES]  # fmt: skip


def test_every_runtime_data_file_is_copied_into_the_image():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    copied = {name for line in re.findall(r"^COPY (data/.+) data/$", dockerfile, re.M) for name in line.split()}
    for path in RUNTIME_DATA:
        assert path.relative_to(ROOT).as_posix() in copied, f"{path.name} is read at runtime but not in the image"
