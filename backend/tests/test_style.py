"""[W7-2-A] Tests for style.py: quadrant proximity (timeline.md section 7.3)
and q* resolution from a stored survey row."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP_DIR / "recommend"))
sys.path.insert(0, str(APP_DIR / "survey"))
import preferences as P  # noqa: E402
import style as S        # noqa: E402


def test_style_is_one_at_the_target():
    assert S.style_score((0.4, -0.3), (0.4, -0.3)) == 1.0


def test_style_is_zero_at_opposite_corners():
    assert S.style_score((1.0, 1.0), (-1.0, -1.0)) == pytest.approx(0.0)


def test_style_is_half_at_the_diagonal_midpoint():
    # distance from (1,1) to (-1,-1) is 2*sqrt(2); the midpoint is sqrt(2) away.
    assert S.style_score((0.0, 0.0), (1.0, 1.0)) == pytest.approx(0.5)


def test_stored_targets_are_used_as_is():
    target, _ = S.resolve_target({"goal_x_target": 0.123, "goal_y_target": -0.456,
                                  "discipline": "boulder"})
    assert target == (0.123, -0.456)


def test_stored_targets_add_no_warning():
    _, warnings = S.resolve_target({"goal_x_target": 0.1, "goal_y_target": 0.2})
    assert warnings == []


def test_null_targets_recompute_the_expected_point():
    survey = {"goal_x_target": None, "goal_y_target": None, "discipline": "sport",
              "terrain": "overhang", "level": "elite"}
    target, _ = S.resolve_target(survey)
    assert target == P.target_quadrant("sport", "overhang", "elite", None)


def test_recompute_adds_the_warning():
    _, warnings = S.resolve_target({"discipline": "sport"})
    assert warnings == ["target_recomputed_without_goal"]


def test_no_discipline_gives_no_target():
    target, _ = S.resolve_target({})
    assert target is None


def test_no_discipline_adds_no_target_warning():
    _, warnings = S.resolve_target({"goal_x_target": None, "goal_y_target": None})
    assert warnings == ["no_target"]


def test_invalid_stored_terrain_raises_value_error():
    with pytest.raises(ValueError):
        S.resolve_target({"discipline": "sport", "terrain": "ice"})


def test_exactly_one_null_target_raises_value_error():
    with pytest.raises(ValueError):
        S.resolve_target({"goal_x_target": 0.5, "goal_y_target": None, "discipline": "trad"})


def test_other_single_null_target_raises_value_error():
    with pytest.raises(ValueError):
        S.resolve_target({"goal_x_target": None, "goal_y_target": 0.5, "discipline": "trad"})


@pytest.mark.parametrize("bad", [1.5, -1.0001, float("nan"), float("inf"), True, "0.5", 10**400])
def test_invalid_stored_target_raises_value_error(bad):
    with pytest.raises(ValueError):
        S.resolve_target({"goal_x_target": bad, "goal_y_target": 0.0})


def test_target_at_plane_boundary_is_accepted():
    target, _ = S.resolve_target({"goal_x_target": -1, "goal_y_target": 1})
    assert target == (-1, 1)


def test_decimal_targets_from_numeric_columns_are_accepted():
    from decimal import Decimal
    target, _ = S.resolve_target({"goal_x_target": Decimal("0.250"),
                                  "goal_y_target": Decimal("-0.500")})
    assert target == (0.25, -0.5)
