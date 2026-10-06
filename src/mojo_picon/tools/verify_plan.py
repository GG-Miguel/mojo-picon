"""Deterministic verification of the Planner's proposals (ADR-05).

The Planner loops propose -> verify_plan -> correct (max. 3 iterations). Each issue carries a
concrete, actionable message ("proteína −18 %") that is fed back to the Planner.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from mojo_picon.domain import Allergen, Food, MacroTargets, Nutrients, Plan

KCAL_TOLERANCE = 0.10  # ±10 % of the remaining kcal (Especificación funcional, CU-05)
# Macros: relative tolerance, with an absolute floor so small remainders are not impossible to hit.
MACRO_TOLERANCE = {"protein_g": (0.15, 10.0), "carbs_g": (0.20, 15.0), "fat_g": (0.20, 8.0)}
MIN_ITEM_GRAMS = 5

_MACRO_NAMES_ES = {"protein_g": "proteína", "carbs_g": "hidratos", "fat_g": "grasas"}


class IssueCode(StrEnum):
    UNKNOWN_FOOD = "unknown_food"
    ALLERGEN = "allergen"
    UNREALISTIC_QUANTITY = "unrealistic_quantity"
    KCAL_OUT_OF_RANGE = "kcal_out_of_range"
    MACRO_OUT_OF_RANGE = "macro_out_of_range"
    NOTHING_REMAINING = "nothing_remaining"


@dataclass(frozen=True)
class Issue:
    code: IssueCode
    message: str  # in Spanish: shown to the Planner and, if it does not converge, to the user


@dataclass(frozen=True)
class VerifyResult:
    passed: bool
    totals: Nutrients
    issues: list[Issue] = field(default_factory=list)


def verify_plan(
    plan: Plan,
    remaining: MacroTargets,
    allergens: frozenset[Allergen],
    foods: Mapping[str, Food],
) -> VerifyResult:
    issues: list[Issue] = []
    totals = Nutrients.zero()

    for item in plan.items:
        food = foods.get(item.food_id)
        if food is None:
            issues.append(Issue(IssueCode.UNKNOWN_FOOD, f"«{item.food_id}» no está en la tabla de alimentos"))
            continue
        totals = totals + food.nutrients_for(item.grams)
        for allergen in sorted(food.allergens & allergens):
            issues.append(Issue(IssueCode.ALLERGEN, f"{food.name} contiene {allergen.value}, alérgeno del usuario"))
        if not MIN_ITEM_GRAMS <= item.grams <= food.max_portion_g:
            issues.append(
                Issue(
                    IssueCode.UNREALISTIC_QUANTITY,
                    f"{food.name}: {item.grams:g} g no es una cantidad realista "
                    f"(entre {MIN_ITEM_GRAMS} y {food.max_portion_g:g} g)",
                )
            )

    if remaining.kcal <= 0:
        issues.append(Issue(IssueCode.NOTHING_REMAINING, "No quedan kcal en el objetivo del día"))
    else:
        issues.extend(_kcal_issue(totals.kcal, remaining.kcal))
        for macro, (relative, absolute) in MACRO_TOLERANCE.items():
            issues.extend(_macro_issue(macro, getattr(totals, macro), getattr(remaining, macro), relative, absolute))

    return VerifyResult(passed=not issues, totals=totals.scaled(1), issues=issues)


def _kcal_issue(planned: float, target: float) -> list[Issue]:
    deviation = (planned - target) / target
    if abs(deviation) <= KCAL_TOLERANCE:
        return []
    return [
        Issue(
            IssueCode.KCAL_OUT_OF_RANGE,
            f"kcal {_percent(deviation)} ({planned:.0f} frente a {target:.0f}; tolerancia ±{KCAL_TOLERANCE:.0%})",
        )
    ]


def _macro_issue(macro: str, planned: float, target: float, relative: float, absolute: float) -> list[Issue]:
    if target <= 0:
        return []  # this macro is already covered for the day; any extra is judged by the kcal check
    if abs(planned - target) <= max(relative * target, absolute):
        return []
    deviation = (planned - target) / target
    return [
        Issue(
            IssueCode.MACRO_OUT_OF_RANGE,
            f"{_MACRO_NAMES_ES[macro]} {_percent(deviation)} ({planned:.0f} g frente a {target:.0f} g)",
        )
    ]


def _percent(deviation: float) -> str:
    sign = "+" if deviation > 0 else "−"
    return f"{sign}{abs(deviation):.0%}".replace("%", " %")
