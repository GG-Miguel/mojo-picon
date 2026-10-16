import pytest

from mojo_picon.domain import ActivityLevel, Goal, Nutrients, Profile, Sex
from mojo_picon.tools.energy import (
    ExtremeGoalError,
    activity_energy,
    calc_bmr,
    calc_tdee,
    daily_balance,
    daily_target,
    load_met_table,
    macro_split,
    minutes_for_distance,
    per_kg_target,
)

RUNNER = Profile(age=34, sex=Sex.MALE, weight_kg=70, height_cm=175, activity_level=ActivityLevel.LIGHT)


# Mifflin-St Jeor reference values, computed by hand:
# male:   10*70 + 6.25*175 - 5*34 + 5   = 1628.75
# female: 10*60 + 6.25*165 - 5*30 - 161 = 1320.25
@pytest.mark.parametrize(
    ("profile", "expected"),
    [
        (RUNNER, 1628.75),
        (Profile(age=30, sex=Sex.FEMALE, weight_kg=60, height_cm=165), 1320.25),
    ],
)
def test_calc_bmr_mifflin_st_jeor(profile, expected):
    assert calc_bmr(profile) == pytest.approx(expected)


def test_calc_tdee_applies_activity_factor_without_training():
    assert calc_tdee(RUNNER) == pytest.approx(1628.75 * 1.3)


def test_macro_split_protein_per_kg_fat_share_and_carbs_remainder():
    m = macro_split(2000, 70)
    assert m.protein_g == pytest.approx(112)  # 1.6 g/kg
    assert m.fat_g == pytest.approx(2000 * 0.30 / 9)
    assert m.protein_g * 4 + m.carbs_g * 4 + m.fat_g * 9 == pytest.approx(2000)


def test_daily_target_maintain_adds_training():
    rest = daily_target(RUNNER)
    run = daily_target(RUNNER, training_kcal=616)
    assert rest.target.kcal == 2117
    assert run.target.kcal == 2117 + 616
    assert not run.clamped_to_bmr


def test_daily_target_never_below_bmr():
    profile = RUNNER.model_copy(update={"goal": Goal.LOSE, "weekly_rate_kg": 1.0, "activity_level": "sedentary"})
    target = daily_target(profile)
    assert target.target.kcal == round(calc_bmr(profile))
    assert target.clamped_to_bmr


def test_extreme_goal_is_rejected():
    profile = RUNNER.model_copy(update={"goal": Goal.LOSE, "weekly_rate_kg": 1.5})
    with pytest.raises(ExtremeGoalError):
        daily_target(profile)


def test_daily_balance_can_be_negative():
    target = macro_split(2000, 70)
    consumed = Nutrients(kcal=2100, protein_g=100, carbs_g=250, fat_g=70)
    remaining = daily_balance(target, consumed)
    assert remaining.kcal == -100
    assert remaining.protein_g == 12


def test_activity_energy_is_net_of_resting_met():
    # 10 km at 9.7 km/h, 70 kg: (9.8 - 1) * 70 * (10 / 9.7) h
    minutes = minutes_for_distance(10, 9.7)
    assert activity_energy(9.8, 70, minutes) == round(8.8 * 70 * 10 / 9.7)


@pytest.mark.parametrize("args", [(0.5, 70, 60), (5, 0, 60), (5, 70, 0)])
def test_activity_energy_rejects_invalid_input(args):
    with pytest.raises(ValueError):
        activity_energy(*args)


def test_met_table_loads():
    table = load_met_table()
    assert table["running_9.7kmh"].met == 9.8
    assert table["weights_moderate"].speed_kmh is None


def test_per_kg_target():
    t = per_kg_target(70, 1.2, 2)
    assert (t.total_min, t.total_max) == (84, 140)


@pytest.mark.parametrize("args", [(0, 1.2, 2), (70, 2, 1.2), (70, 15, None)])
def test_per_kg_target_rejects_invalid_input(args):
    with pytest.raises(ValueError):
        per_kg_target(*args)


def test_planning_targets_are_always_reachable_after_exceeding_a_macro():
    from mojo_picon.domain import MacroTargets
    from mojo_picon.tools.energy import planning_targets

    # Seen on 2026-10-16: fat already exceeded, 251 g of carbs (~1004 kcal) with 886 kcal left
    remaining = MacroTargets(kcal=886, protein_g=30, carbs_g=251, fat_g=-6)
    targets, notes = planning_targets(remaining)
    assert targets.fat_g == 0 and notes == ["ya has superado la grasa del día"]
    energy = targets.protein_g * 4 + targets.carbs_g * 4 + targets.fat_g * 9
    assert abs(energy - 886) <= 886 * 0.02  # the macros now add up to the kcal that remain
    assert targets.carbs_g < 251 and targets.protein_g < 30


def test_planning_targets_leave_consistent_remainders_alone():
    from mojo_picon.domain import MacroTargets
    from mojo_picon.tools.energy import planning_targets

    remaining = MacroTargets(kcal=900, protein_g=50, carbs_g=110, fat_g=28)  # 892 kcal from macros
    assert planning_targets(remaining) == (remaining, [])
    nothing_left = MacroTargets(kcal=-50, protein_g=-5, carbs_g=10, fat_g=-2)
    assert planning_targets(nothing_left) == (nothing_left, [])  # verify_plan says nothing remains
