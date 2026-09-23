"""[W4'-2] Tests for preferences.py: preference inputs -> target q*
(discipline/terrain/level/goal), timeline.md sections 3 and 7.5.

Loads preferences.py the same way test_survey.py loads schema.py / anchors.py
/ store.py: sys.path.insert of the survey directory, then a bare import.
schema.py is loaded the same way (test_survey.py already proves this is
collision-free) so these tests can pin preferences.py's vocabulary and output
precision against it -- see preferences.py's own module docstring for why
preferences.py itself does NOT import schema.py (stdlib-only, independent).

Section 3 (the quadrant framework) and section 7.5 (q* derived from
preference answers, "assert each of the four disciplines lands in the
quadrant section 3 associates with it") are the acceptance criteria this
file targets.
"""

from __future__ import annotations

import itertools
import math
import subprocess
import sys
from pathlib import Path

import pytest

SURVEY_DIR = Path(__file__).resolve().parents[1] / "app" / "survey"
sys.path.insert(0, str(SURVEY_DIR))
import preferences as P  # noqa: E402
import schema as S       # noqa: E402


# Section 3: which quadrant each discipline belongs to. Reproduced here
# (not imported from preferences.py) so a bug that hardcodes the same wrong
# mapping in both places cannot hide from these tests.
DISCIPLINE_QUADRANT = {
    "boulder": "Q4",
    "sport": "Q1",
    "trad": "Q2",
    "gym": "Q3",
}

DISCIPLINES = sorted(S.ENUMS["discipline"])
TERRAINS = sorted(S.PY_ONLY_ENUMS["terrain"])
LEVELS = sorted(S.PY_ONLY_ENUMS["level"])
GOALS = [None, -1, -0.5, 0, 0.5, 1]

EXHAUSTIVE = list(itertools.product(
    DISCIPLINES, TERRAINS + [None], LEVELS + [None], GOALS,
))


def _quadrant(x: float, y: float) -> str:
    """Independent, local reimplementation of the section 3 quadrant test --
    deliberately NOT calling P.quadrant_of, so a bug shared by both
    target_quadrant() and quadrant_of() could not hide from these tests."""
    if x > 0 and y < 0:
        return "Q1"
    if x < 0 and y < 0:
        return "Q2"
    if x < 0 and y > 0:
        return "Q3"
    if x > 0 and y > 0:
        return "Q4"
    raise AssertionError(f"({x}, {y}) sits on an axis -- no quadrant")


# ==========================================================================
# 1. Each discipline, all optionals None, lands in its section 3 quadrant
# ==========================================================================

@pytest.mark.parametrize("discipline,expected", sorted(DISCIPLINE_QUADRANT.items()))
def test_discipline_alone_lands_in_its_section_3_quadrant(discipline, expected):
    x, y = P.target_quadrant(discipline)
    assert _quadrant(x, y) == expected


# ==========================================================================
# 2. Exhaustive: discipline x terrain x level x goal, every combination
# ==========================================================================

def test_exhaustive_matrix_covers_600_combinations():
    """Sanity check on the matrix itself, mirroring test_survey.py's own
    'sanity check on the parser' -- if this fails, later passes in this
    section would be comparing against a matrix that silently shrank."""
    assert len(EXHAUSTIVE) == len(DISCIPLINES) * (len(TERRAINS) + 1) * (len(LEVELS) + 1) * len(GOALS)
    assert len(EXHAUSTIVE) == 600


@pytest.mark.parametrize("discipline,terrain,level,goal", EXHAUSTIVE)
def test_exhaustive_combination_stays_in_range_off_axis_and_in_quadrant(
    discipline, terrain, level, goal
):
    x, y = P.target_quadrant(discipline, terrain, level, goal)
    assert -1 <= x <= 1 and -1 <= y <= 1
    assert x != 0 and y != 0
    assert abs(x) >= 0.1 and abs(y) >= 0.1
    assert _quadrant(x, y) == DISCIPLINE_QUADRANT[discipline]


# ==========================================================================
# 3. Vocabulary drift pins
# ==========================================================================

def test_discipline_base_matches_schema_discipline_enum():
    assert set(P.DISCIPLINE_BASE) == S.ENUMS["discipline"]


def test_terrain_offset_matches_schema_terrain_enum():
    assert set(P.TERRAIN_OFFSET) == S.PY_ONLY_ENUMS["terrain"]


def test_level_offset_matches_schema_level_enum():
    assert set(P.LEVEL_OFFSET) == S.PY_ONLY_ENUMS["level"]


def test_output_decimals_matches_schema_goal_target_decimals():
    assert P.OUTPUT_DECIMALS == S.GOAL_TARGET_DECIMALS


# ==========================================================================
# 4. Directional nudges
# ==========================================================================

@pytest.mark.parametrize("discipline", DISCIPLINES)
@pytest.mark.parametrize(
    "terrain,dx_sign,dy_sign",
    [
        ("overhang", +1, +1),  # -> Q4: toward +x/+y
        ("slab", -1, +1),      # -> Q3: toward -x/+y
        ("crack", -1, -1),     # -> Q2: toward -x/-y
        ("vertical", +1, -1),  # -> Q1: toward +x/-y
    ],
)
def test_terrain_nudges_toward_its_own_section_3_quadrant(discipline, terrain, dx_sign, dy_sign):
    bx, by = P.target_quadrant(discipline)
    tx, ty = P.target_quadrant(discipline, terrain=terrain)
    assert (tx - bx) * dx_sign > 0, f"{terrain} did not move x the expected direction"
    assert (ty - by) * dy_sign > 0, f"{terrain} did not move y the expected direction"


@pytest.mark.parametrize("discipline", DISCIPLINES)
@pytest.mark.parametrize("terrain", TERRAINS + [None])
def test_level_is_monotone_non_decreasing_in_x(discipline, terrain):
    xs = [
        P.target_quadrant(discipline, terrain, level, None)[0]
        for level in ("beginner", "intermediate", "advanced", "elite")
    ]
    assert xs == sorted(xs)


@pytest.mark.parametrize("discipline", DISCIPLINES)
@pytest.mark.parametrize("level", LEVELS + [None])
def test_goal_is_monotone_in_x(discipline, level):
    xs = [
        P.target_quadrant(discipline, None, level, goal)[0]
        for goal in (-1, -0.5, 0, 0.5, 1)
    ]
    assert xs == sorted(xs)


@pytest.mark.parametrize("discipline", DISCIPLINES)
def test_level_leaves_y_unchanged(discipline):
    ys = {
        P.target_quadrant(discipline, level=level)[1]
        for level in ("beginner", "intermediate", "advanced", "elite", None)
    }
    assert len(ys) == 1


@pytest.mark.parametrize("discipline", DISCIPLINES)
def test_goal_leaves_y_unchanged(discipline):
    ys = {
        P.target_quadrant(discipline, goal=goal)[1]
        for goal in (-1, -0.5, 0, 0.5, 1, None)
    }
    assert len(ys) == 1


# ==========================================================================
# 5. Output storable: schema.validate() accepts the full exhaustive product
# ==========================================================================

@pytest.mark.parametrize("discipline,terrain,level,goal", EXHAUSTIVE)
def test_output_is_storable_per_schema_validate(discipline, terrain, level, goal):
    x, y = P.target_quadrant(discipline, terrain, level, goal)
    payload = {"discipline": discipline, "goal_x_target": x, "goal_y_target": y}
    if terrain is not None:
        payload["terrain"] = terrain
    if level is not None:
        payload["level"] = level
    assert S.validate(payload) == []


# ==========================================================================
# 6. Rejections
# ==========================================================================

@pytest.mark.parametrize("discipline", ["approach", "", "BOULDER", 3, 3.5, True, None])
def test_rejects_unknown_or_wrongly_typed_discipline(discipline):
    """Covers unknown ('approach', '', case-sensitivity 'BOULDER'), non-str
    (3, 3.5, True) and None in one parametrized sweep."""
    with pytest.raises(ValueError):
        P.target_quadrant(discipline)


@pytest.mark.parametrize("terrain", ["mountain", "SLAB", 3, 3.5, True])
def test_rejects_unknown_or_wrongly_typed_terrain(terrain):
    with pytest.raises(ValueError):
        P.target_quadrant("boulder", terrain=terrain)


@pytest.mark.parametrize("level", ["pro", "BEGINNER", 3, 3.5, True])
def test_rejects_unknown_or_wrongly_typed_level(level):
    with pytest.raises(ValueError):
        P.target_quadrant("boulder", level=level)


@pytest.mark.parametrize(
    "goal",
    [True, False, "0.5", "1", math.nan, math.inf, -math.inf, 1.01, -1.01, 100, -100,
     # an int too large for a float: must be ValueError, not OverflowError
     10**400, -10**400],
)
def test_rejects_invalid_goal(goal):
    with pytest.raises(ValueError):
        P.target_quadrant("boulder", goal=goal)


@pytest.mark.parametrize("goal", [-1, -1.0, 1, 1.0])
def test_goal_boundary_values_are_inclusive_not_rejected(goal):
    """-1 and 1 are the closed interval endpoints -- must NOT raise."""
    assert P.target_quadrant("boulder", goal=goal) is not None


def test_unknown_discipline_message_names_field_and_allowed_set():
    with pytest.raises(ValueError) as exc_info:
        P.target_quadrant("approach")
    msg = str(exc_info.value)
    assert "discipline" in msg
    for value in S.ENUMS["discipline"]:
        assert value in msg


def test_non_str_discipline_message_names_field_and_allowed_set():
    with pytest.raises(ValueError) as exc_info:
        P.target_quadrant(3)
    msg = str(exc_info.value)
    assert "discipline" in msg
    for value in S.ENUMS["discipline"]:
        assert value in msg


def test_unknown_terrain_message_names_field_and_allowed_set():
    with pytest.raises(ValueError) as exc_info:
        P.target_quadrant("boulder", terrain="mountain")
    msg = str(exc_info.value)
    assert "terrain" in msg
    for value in S.PY_ONLY_ENUMS["terrain"]:
        assert value in msg


def test_unknown_level_message_names_field_and_allowed_set():
    with pytest.raises(ValueError) as exc_info:
        P.target_quadrant("boulder", level="pro")
    msg = str(exc_info.value)
    assert "level" in msg
    for value in S.PY_ONLY_ENUMS["level"]:
        assert value in msg


# ==========================================================================
# 7. Purity / determinism
# ==========================================================================

def test_same_inputs_give_the_same_output():
    a = P.target_quadrant("sport", "vertical", "advanced", 0.5)
    b = P.target_quadrant("sport", "vertical", "advanced", 0.5)
    assert a == b


@pytest.mark.parametrize("table_name", ["DISCIPLINE_BASE", "TERRAIN_OFFSET", "LEVEL_OFFSET"])
def test_module_tables_are_immutable(table_name):
    """Guards the 'tables are not mutated' contract structurally: a
    MappingProxyType raises on the FIRST attempted mutation, rather than
    this test merely hoping nothing changed after the fact."""
    table = getattr(P, table_name)
    key = next(iter(table))
    with pytest.raises(TypeError):
        table[key] = table[key]


def test_nudge_budget_invariant_holds():
    """Pins the exact structural invariant: 3 * NUDGE < BASE_MAGNITUDE (a
    nudge can never cross an axis), and the minimum |coordinate| is exactly
    0.10. Also checked at import time in preferences.py itself; this pins
    the specific numbers so a change to either constant is a deliberate,
    visible test edit rather than a silent behavior change."""
    budget = 3 * P.NUDGE
    assert budget < P.BASE_MAGNITUDE
    assert P.BASE_MAGNITUDE - budget == pytest.approx(0.10)
    assert P.BASE_MAGNITUDE + budget <= 1.0


@pytest.mark.parametrize("base,nudge", [(0.40, 0.15), (0.55, 0.20), (0.70, 0.15)])
def test_nudge_budget_check_raises_when_violated(base, nudge):
    """The import-time guard is an explicit raise, not an `assert`, so it
    still fires under `python -O`. (0.40, 0.15): budget exceeds base, q* could
    cross an axis; (0.55, 0.20): same, via NUDGE; (0.70, 0.15): max
    |coordinate| 1.15 leaves the plane."""
    with pytest.raises(RuntimeError):
        P._check_nudge_budget(base, nudge)


def test_import_time_check_survives_python_O():
    code = (
        f"import sys; sys.path.insert(0, {str(SURVEY_DIR)!r}); "
        f"import preferences as P; P._check_nudge_budget(0.40, 0.15)"
    )
    r = subprocess.run([sys.executable, "-O", "-c", code], capture_output=True, text=True)
    assert r.returncode != 0 and "RuntimeError" in r.stderr


# ==========================================================================
# 8. Golden fixtures (arithmetic verified by hand -- see the card spec)
# ==========================================================================

@pytest.mark.parametrize(
    "discipline,terrain,level,goal,expected",
    [
        ("boulder", "overhang", "elite", 1, (1.0, 0.7)),
        ("gym", "slab", "beginner", None, (-0.85, 0.7)),
        ("trad", "crack", "advanced", -1, (-0.8, -0.7)),
    ],
)
def test_golden_fixtures(discipline, terrain, level, goal, expected):
    assert P.target_quadrant(discipline, terrain, level, goal) == expected


# ==========================================================================
# Bonus: quadrant_of() helper (optional per the card spec; useful to W6-1)
# ==========================================================================

@pytest.mark.parametrize("discipline,expected", sorted(DISCIPLINE_QUADRANT.items()))
def test_quadrant_of_matches_target_quadrant(discipline, expected):
    q = P.target_quadrant(discipline)
    assert P.quadrant_of(q) == expected


@pytest.mark.parametrize("q", [
    (0.0, 0.5), (0.5, 0.0), (0.0, 0.0),
    (math.nan, 0.5), (0.5, math.nan), (math.inf, 0.5), (0.5, -math.inf),
])
def test_quadrant_of_rejects_a_point_on_an_axis_or_non_finite(q):
    with pytest.raises(ValueError):
        P.quadrant_of(q)
