"""Energy calculations: BMR, TDEE, daily targets, training energy and per-kg amounts.

Deterministic and tested: every number the user sees comes from here or from another
tool, never from the model (Principles #1, ADR-05).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from mojo_picon.domain import ActivityLevel, Goal, MacroTargets, Nutrients, Profile, Sex
from mojo_picon.domain.profile import MAX_WEEKLY_RATE_KG  # the profile rejects faster rates too

# Multipliers over BMR for daily life **without training** (trainings are added with
# activity_energy). Provisional values: to be validated by the author and cited in the
# expert brief before the demo.
ACTIVITY_FACTORS: dict[ActivityLevel, float] = {
    ActivityLevel.SEDENTARY: 1.2,
    ActivityLevel.LIGHT: 1.3,
    ActivityLevel.MODERATE: 1.4,
    ActivityLevel.HIGH: 1.5,
}

KCAL_PER_KG_BODY_WEIGHT = 7700  # usual approximation for 1 kg of body weight change

# Default macro split. Provisional: to be taken from the expert brief (with source tag).
PROTEIN_G_PER_KG = 1.6
FAT_KCAL_SHARE = 0.30
KCAL_PER_G = {"protein": 4, "carbs": 4, "fat": 9}

MAX_PER_KG_VALUE = 10  # no nutrient reference is above 10 g/kg; protects against model mistakes

DEFAULT_MET_TABLE = Path(__file__).resolve().parents[3] / "data" / "met_table.csv"


class ExtremeGoalError(ValueError):
    """The requested weight change is faster than the safe limit."""


@dataclass(frozen=True)
class DailyTarget:
    bmr: float
    tdee: float
    goal_adjustment: float
    training_kcal: float
    target: MacroTargets
    clamped_to_bmr: bool  # the goal would have put the target below BMR


@dataclass(frozen=True)
class MetActivity:
    id: str
    name: str
    met: float
    speed_kmh: float | None
    source: str


@dataclass(frozen=True)
class PerKgTarget:
    per_kg_min: float
    per_kg_max: float
    weight_kg: float
    total_min: float
    total_max: float
    unit: str


def calc_bmr(profile: Profile) -> float:
    """Basal metabolic rate with the Mifflin-St Jeor equation (kcal/day)."""
    base = 10 * profile.weight_kg + 6.25 * profile.height_cm - 5 * profile.age
    return base + (5 if profile.sex is Sex.MALE else -161)


def calc_tdee(profile: Profile) -> float:
    """Total daily energy expenditure without training (kcal/day)."""
    return calc_bmr(profile) * ACTIVITY_FACTORS[profile.activity_level]


def goal_adjustment(profile: Profile) -> float:
    """Daily kcal to add (gain) or subtract (lose) for the weekly rate of the profile."""
    if profile.goal is Goal.MAINTAIN:
        return 0.0
    if profile.weekly_rate_kg > MAX_WEEKLY_RATE_KG:
        raise ExtremeGoalError(
            f"A change of {profile.weekly_rate_kg:g} kg per week is above the safe limit of {MAX_WEEKLY_RATE_KG:g} kg."
        )
    daily = profile.weekly_rate_kg * KCAL_PER_KG_BODY_WEIGHT / 7
    return -daily if profile.goal is Goal.LOSE else daily


def macro_split(kcal: float, weight_kg: float) -> MacroTargets:
    protein_g = PROTEIN_G_PER_KG * weight_kg
    fat_g = kcal * FAT_KCAL_SHARE / KCAL_PER_G["fat"]
    carbs_kcal = kcal - protein_g * KCAL_PER_G["protein"] - fat_g * KCAL_PER_G["fat"]
    return MacroTargets(kcal=kcal, protein_g=protein_g, carbs_g=max(carbs_kcal, 0) / KCAL_PER_G["carbs"], fat_g=fat_g)


def daily_target(profile: Profile, training_kcal: float = 0.0) -> DailyTarget:
    """Target for the day: TDEE + goal adjustment + logged training, never below BMR."""
    bmr = calc_bmr(profile)
    tdee = calc_tdee(profile)
    adjustment = goal_adjustment(profile)
    kcal = tdee + adjustment + training_kcal
    clamped = kcal < bmr
    kcal = max(kcal, bmr)
    return DailyTarget(
        bmr=round(bmr),
        tdee=round(tdee),
        goal_adjustment=round(adjustment),
        training_kcal=round(training_kcal),
        target=_rounded(macro_split(kcal, profile.weight_kg)),
        clamped_to_bmr=clamped,
    )


def daily_balance(target: MacroTargets, consumed: Nutrients) -> MacroTargets:
    """What remains of the day's target. Negative values mean the target is exceeded."""
    return _rounded(
        MacroTargets(
            kcal=target.kcal - consumed.kcal,
            protein_g=target.protein_g - consumed.protein_g,
            carbs_g=target.carbs_g - consumed.carbs_g,
            fat_g=target.fat_g - consumed.fat_g,
        )
    )


MACRO_KCAL_PER_G = {f"{macro}_g": kcal for macro, kcal in KCAL_PER_G.items()}
MACRO_NAMES = {"protein_g": "la proteína", "carbs_g": "los hidratos", "fat_g": "la grasa"}


def planning_targets(remaining: MacroTargets) -> tuple[MacroTargets, list[str]]:
    """What a plan for the rest of the day can aim at, and notes for the user.

    What remains can be inconsistent once a macro is exceeded: after going over on fat, the other
    remainders can add up to more kcal than remain (seen on 2026-10-16: 251 g of carbohydrate, about
    1004 kcal, with 886 kcal left), and no plan can pass. An exceeded macro becomes 0 (the plan is low
    in it) and the others are rescaled so that their energy equals the kcal that remain.
    """
    if remaining.kcal <= 0:
        return remaining, []
    macros = {m: max(getattr(remaining, m), 0.0) for m in MACRO_KCAL_PER_G}
    notes = [f"ya has superado {MACRO_NAMES[m]} del día" for m in MACRO_KCAL_PER_G if getattr(remaining, m) <= 0]
    energy = sum(macros[m] * MACRO_KCAL_PER_G[m] for m in MACRO_KCAL_PER_G)
    if energy <= 0:
        return MacroTargets(kcal=remaining.kcal, **macros), notes
    factor = remaining.kcal / energy
    if abs(factor - 1) > 0.05:  # only when the remainders really disagree with the kcal left
        macros = {m: v * factor for m, v in macros.items()}
    return _rounded(MacroTargets(kcal=remaining.kcal, **macros)), notes


def load_met_table(path: Path = DEFAULT_MET_TABLE) -> dict[str, MetActivity]:
    with path.open(encoding="utf-8") as f:
        return {
            row["id"]: MetActivity(
                id=row["id"],
                name=row["name"],
                met=float(row["met"]),
                speed_kmh=float(row["speed_kmh"]) if row["speed_kmh"] else None,
                source=row["source"],
            )
            for row in csv.DictReader(f)
        }


def activity_energy(met: float, weight_kg: float, minutes: float) -> float:
    """Net kcal of a training session: (MET - 1) x kg x hours.

    One MET is the resting rate, already counted in the TDEE; subtracting it avoids
    counting rest twice.
    """
    if met < 1 or weight_kg <= 0 or minutes <= 0:
        raise ValueError("MET must be >= 1, and weight and duration positive")
    return round((met - 1) * weight_kg * minutes / 60)


def minutes_for_distance(distance_km: float, speed_kmh: float) -> float:
    if distance_km <= 0 or speed_kmh <= 0:
        raise ValueError("distance and speed must be positive")
    return distance_km / speed_kmh * 60


def per_kg_target(weight_kg: float, per_kg_min: float, per_kg_max: float | None = None, unit: str = "g") -> PerKgTarget:
    """Turn a per-kg reference (e.g. 1.2-2 g/kg of protein, cited from the expert brief) into
    the user's amount. The weight comes from the profile, never from the model (ADR-19)."""
    per_kg_max = per_kg_min if per_kg_max is None else per_kg_max
    if weight_kg <= 0 or per_kg_min < 0 or per_kg_max < per_kg_min:
        raise ValueError("invalid per-kg target")
    if per_kg_max > MAX_PER_KG_VALUE:
        raise ValueError("per-kg value out of plausible range")
    return PerKgTarget(
        per_kg_min=per_kg_min,
        per_kg_max=per_kg_max,
        weight_kg=weight_kg,
        total_min=round(per_kg_min * weight_kg),
        total_max=round(per_kg_max * weight_kg),
        unit=unit,
    )


def _rounded(t: MacroTargets) -> MacroTargets:
    return MacroTargets(
        kcal=round(t.kcal), protein_g=round(t.protein_g), carbs_g=round(t.carbs_g), fat_g=round(t.fat_g)
    )
