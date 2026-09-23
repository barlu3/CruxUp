"""[W4'-2] Preference inputs -> target q* (discipline/terrain/level/goal).

Turns a subset of the questionnaire's preference answers (timeline.md
section 7.5) into q* = (x, y), the point on the section 3 quadrant plane a
user is aiming for. Pure arithmetic, no IO: `target_quadrant()` takes
already-shaped values and returns a coordinate. Validating the REST of a
submission (shape, allowed keys, the other scalar fields) is schema.py's
job, and resolving anchor shoes is anchors.py's job -- store.py is expected
to compose all three, exactly as schema.py's own module docstring already
describes for itself and anchors.py.

Section 3 quadrant map (reproduced here as this module's ground truth):

    Q1 (x>0, y<0): performance + stiff -- sport, technical face,
                   precision edging, board last
    Q2 (x<0, y<0): comfort + stiff     -- all-day trad, big wall,
                   wide toe box, multi-pitch
    Q3 (x<0, y>0): comfort + soft      -- gym, beginner, slabs,
                   neutral shape, slip-on
    Q4 (x>0, y>0): performance + soft  -- bouldering, steep terrain,
                   aggressive downturn, soft rand

Section 7.5 lists SIX preference inputs: discipline, terrain, experience
level, comfort-vs-performance goal, stiffness preference, and
downsizing/pain tolerance. This card's scope is the first four only.
Stiffness preference and downsizing/pain tolerance are DEFERRED: section 7.5
gives no mapping for either (stiffness would presumably move y; downsizing /
pain tolerance is a sizing concern, not a quadrant one), and inventing one
here is a judgement call for a future card, not this one.

Design
------
`discipline` is REQUIRED and picks a quadrant outright (DISCIPLINE_BASE).
`terrain` / `level` / `goal` are each optional and only NUDGE q* within that
quadrant -- they move the point around, but by construction (see the
"structural invariant" below) never far enough to reach an axis or cross
into a different quadrant. A caller who supplies only `discipline` still
gets a valid, storable q* -- every other input left at None contributes zero
offset on every axis it would otherwise touch.

  * TERRAIN_OFFSET pushes q* (magnitude NUDGE on BOTH axes) toward the
    section 3 quadrant terrain is itself associated with: vertical -> Q1,
    crack -> Q2, slab -> Q3, overhang -> Q4.
  * LEVEL_OFFSET moves x ONLY. Section 3 lists "beginner" under comfort, so
    beginner is comfort-ward (negative) and elite is performance-ward
    (positive); y is deliberately left untouched -- section 3 does not say
    experience implies anything about stiffness, and inventing that claim is
    exactly what section 7.5's deferred "stiffness preference" question is
    for, not this one. The four levels sit at evenly spaced fractions of
    NUDGE (-1, -1/3, +1/3, +1), landing on -0.15 / -0.05 / +0.05 / +0.15.
  * `goal` moves x ONLY, linearly: NUDGE * goal, for goal in [-1, 1] (-1 =
    full comfort, +1 = full performance -- this is section 3's x-axis
    itself, restricted to a nudge-sized slice of it).

Structural invariant (by construction, not by clamping)
---------------------------------------------------------
Per axis, the worst case is all applicable optional nudges pointed the same
way, against the discipline's own sign. x can receive up to three
NUDGE-sized contributions (terrain, level, goal); y can receive at most one
(terrain only) -- so the general, conservative bound is three:

    3 * NUDGE = 0.45  <  BASE_MAGNITUDE = 0.55

Because the nudge budget is strictly smaller than the base magnitude, the
discipline's sign always wins:

    |coordinate|  >=  BASE_MAGNITUDE - 3*NUDGE  =  0.55 - 0.45  =  0.10  >  0

so q* can NEVER land on an axis (no undefined quadrant) and NEVER leave the
discipline's quadrant, for ANY combination of terrain/level/goal -- not just
the ones exercised by a particular test. This is checked ARITHMETICALLY at
import time immediately below the constants, so an edit to BASE_MAGNITUDE or
NUDGE that breaks the guarantee fails immediately for every caller, not only
when a particular test happens to run; test_preferences.py's exhaustive test
additionally checks the guarantee empirically against every enum
combination.

The best case is bounded too: BASE_MAGNITUDE + 3*NUDGE = 0.55 + 0.45 = 1.00,
exactly the top of section 3's [-1, 1] plane. The defensive
`max(-1.0, min(1.0, ...))` clamp in target_quadrant() is therefore PROVABLY a
no-op for every valid input -- kept only as a backstop against a future
constant change, which the import-time check below would already have caught first.

Rounding
--------
Output is rounded to OUTPUT_DECIMALS, matching goal_x_target / goal_y_target
NUMERIC(4,3) (schema.GOAL_TARGET_DECIMALS), so q* is directly storable and
passes schema._check_goal's scale check rather than being silently rounded
further by Postgres. OUTPUT_DECIMALS is kept as a local constant rather than
importing schema.py, so this module stays stdlib-only and independent of it
(test_preferences.py pins the two constants equal instead).

Error handling, deliberately DIFFERENT from schema.validate()
----------------------------------------------------------------
schema.validate() and anchors.resolve_anchors() both ACCUMULATE every
problem they find, because they front an end-user submission where seeing
every mistake in one round trip matters. target_quadrant() is a pure
coordinate computation one step downstream of that validation, not a form,
so it raises ValueError on the FIRST bad input instead. A caller (store.py,
or a future survey endpoint) is expected to already have run
schema.validate() over the raw submission; this module is not a substitute
for that.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from types import MappingProxyType

# ---------------------------------------------------------------------------
# Magnitudes -- the two judgement-call numbers everything else derives from
# ---------------------------------------------------------------------------

# Per-axis |coordinate| contributed by discipline alone, before any nudge.
BASE_MAGNITUDE = 0.55

# Per-axis |offset| contributed by EACH of terrain / level / goal. Shared
# across all three so the budget inequality below (3 * NUDGE < BASE_MAGNITUDE)
# is one number to keep in sync, not three drifting independently.
NUDGE = 0.15

# ---------------------------------------------------------------------------
# Discipline sets the quadrant (sections 3 and 7.5). MappingProxyType makes
# "the tables are not mutated" (see the module docstring) enforced, not just
# promised in a comment: any attempted write raises TypeError immediately.
# ---------------------------------------------------------------------------
DISCIPLINE_BASE: Mapping[str, tuple[float, float]] = MappingProxyType({
    "sport":   (+BASE_MAGNITUDE, -BASE_MAGNITUDE),  # Q1: performance + stiff
    "trad":    (-BASE_MAGNITUDE, -BASE_MAGNITUDE),  # Q2: comfort + stiff
    "gym":     (-BASE_MAGNITUDE, +BASE_MAGNITUDE),  # Q3: comfort + soft
    "boulder": (+BASE_MAGNITUDE, +BASE_MAGNITUDE),  # Q4: performance + soft
})

# Terrain nudges q* toward the section 3 quadrant IT is associated with, on
# both axes at once.
TERRAIN_OFFSET: Mapping[str, tuple[float, float]] = MappingProxyType({
    "vertical": (+NUDGE, -NUDGE),  # -> Q1: technical face / precision edging
    "crack":    (-NUDGE, -NUDGE),  # -> Q2: cracks-ish, multi-pitch
    "slab":     (-NUDGE, +NUDGE),  # -> Q3: beginner, slabs
    "overhang": (+NUDGE, +NUDGE),  # -> Q4: steep terrain
})

# Level nudges x ONLY -- see "Design" in the module docstring for why y is
# untouched. Four values evenly spaced across [-NUDGE, +NUDGE] (step
# 2*NUDGE/3 = 0.10 between adjacent levels): a comfort-ward pair (beginner
# furthest out, intermediate nearer neutral) and a performance-ward pair
# (advanced nearer neutral, elite furthest out).
LEVEL_OFFSET: Mapping[str, float] = MappingProxyType({
    "beginner":     -NUDGE,
    "intermediate": -NUDGE / 3,
    "advanced":     +NUDGE / 3,
    "elite":        +NUDGE,
})

# Structural invariant, checked at IMPORT TIME -- see "Structural invariant"
# in the module docstring. If a future edit to BASE_MAGNITUDE or NUDGE ever
# let the maximum possible nudge reach or exceed the discipline base, this
# fails immediately for every caller, not only when a particular test runs.
# An explicit `raise`, not `assert`: `python -O` / PYTHONOPTIMIZE strips
# assert statements, which would silently turn this guarantee off in exactly
# the kind of deployment where nobody is watching for it.
def _check_nudge_budget(base: float, nudge: float) -> None:
    budget = 3 * nudge  # terrain + level + goal, each up to `nudge` on x
    if not budget < base:
        raise RuntimeError(
            f"nudge budget {budget} must stay below BASE_MAGNITUDE {base}, or "
            f"a nudge could push q* onto an axis or across a quadrant boundary"
        )
    if not base + budget <= 1.0:
        raise RuntimeError(
            f"max |coordinate| {base + budget} must fit the section 3 plane "
            f"[-1, 1] without relying on the defensive clamp in target_quadrant()"
        )


_check_nudge_budget(BASE_MAGNITUDE, NUDGE)

# comfort-vs-performance slider range accepted for `goal`. Numerically the
# same [-1, 1] as section 3's plane (GOAL_TARGET_MIN/MAX in schema.py), but
# this bounds a raw INPUT slider, not the stored OUTPUT coordinate, so it is
# kept separate here rather than pinned equal to schema.py by a test (only
# OUTPUT_DECIMALS is -- see the module docstring).
GOAL_MIN, GOAL_MAX = -1.0, 1.0

# Mirrors schema.GOAL_TARGET_DECIMALS (goal_x_target / goal_y_target are
# NUMERIC(4,3)). Kept local rather than importing schema.py -- this module is
# stdlib-only and independent of it; test_preferences.py pins the two
# constants equal instead.
OUTPUT_DECIMALS = 3


def _is_number(v: object) -> bool:
    """True for int/float, explicitly False for bool.

    bool is an int subclass in Python (isinstance(True, int) is True), so a
    naive isinstance(v, (int, float)) lets a boolean silently pass as a
    number. Duplicated from schema.py's identical guard rather than
    imported, so this module stays stdlib-only and independent of it (see
    the module docstring).
    """
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _check_enum_value(field: str, value: object, allowed: Mapping[str, object]) -> None:
    """Raise ValueError naming `field` and its allowed set unless `value` is
    a string key of `allowed`. Mirrors schema._check_enum's two messages
    (wrong type / unknown value), but RAISES on the first problem instead of
    returning an accumulated list -- see the module docstring."""
    names = sorted(allowed)
    if not isinstance(value, str):
        raise ValueError(
            f"{field} must be a string, got {type(value).__name__} "
            f"(allowed: {names})"
        )
    if value not in allowed:
        raise ValueError(f"{field}={value!r} not in {names}")


def _check_goal(value: object) -> None:
    """Raise ValueError unless `value` is a finite real number in
    [GOAL_MIN, GOAL_MAX]. bool is rejected by _is_number; NaN/+-inf are
    checked explicitly (rather than left to the range comparison, which is
    silently False for NaN and merely misleading for +-inf) so the message
    names the actual problem.

    Only a float can be non-finite, so only a float goes through
    math.isfinite: an int too large for a float (e.g. 10**400, which
    json.loads happily produces from a long digit string) would otherwise
    raise OverflowError there instead of ValueError. Python compares int
    with float exactly, so the range check below handles it without
    converting."""
    if not _is_number(value):
        raise ValueError(f"goal must be a number, got {type(value).__name__}")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"goal={value} must be finite")
    if not (GOAL_MIN <= value <= GOAL_MAX):
        raise ValueError(f"goal={value} outside [{GOAL_MIN}, {GOAL_MAX}]")


def target_quadrant(
    discipline: str,
    terrain: str | None = None,
    level: str | None = None,
    goal: float | None = None,
) -> tuple[float, float]:
    """Compute q* = (x, y) on the section 3 plane from preference answers.

    `discipline` is REQUIRED and picks the quadrant (DISCIPLINE_BASE).
    `terrain` / `level` / `goal` are optional; None contributes zero offset
    on every axis it would otherwise touch. Raises ValueError -- on the
    first problem found, not accumulated (see the module docstring) -- for
    an unrecognised or non-string discipline/terrain/level, or a `goal` that
    is not a finite number in [-1, 1] (bool and numeric strings are both
    rejected; see _is_number / _check_goal).

    Pure and deterministic: the same inputs always give the same output, no
    IO is performed, and none of the module-level tables are ever mutated.
    """
    _check_enum_value("discipline", discipline, DISCIPLINE_BASE)
    x, y = DISCIPLINE_BASE[discipline]

    if terrain is not None:
        _check_enum_value("terrain", terrain, TERRAIN_OFFSET)
        dx, dy = TERRAIN_OFFSET[terrain]
        x, y = x + dx, y + dy

    if level is not None:
        _check_enum_value("level", level, LEVEL_OFFSET)
        x += LEVEL_OFFSET[level]

    if goal is not None:
        _check_goal(goal)
        x += NUDGE * goal

    # Defensive clamp: PROVABLY a no-op for any valid input -- see
    # "Structural invariant" in the module docstring and the import-time check
    # immediately after LEVEL_OFFSET above, which checks the arithmetic that
    # makes it so.
    x = max(-1.0, min(1.0, x))
    y = max(-1.0, min(1.0, y))

    return round(x, OUTPUT_DECIMALS), round(y, OUTPUT_DECIMALS)


def quadrant_of(q: tuple[float, float]) -> str:
    """Return "Q1".."Q4" for point `q` per section 3. Raises ValueError if
    `q` has a non-finite coordinate or sits on an axis (x == 0 or y == 0) --
    target_quadrant() itself never produces such a point (see the structural
    invariant above), but a caller-built or hand-supplied `q` might. Not
    required by this card, but useful to tests here and to W6-2's
    interactive quadrant.

    catalog/priors.quadrant() classifies the same plane for shoe placements
    but returns an "ON-AXIS" label instead of raising. It is not reused here
    because priors.py imports yaml and this module is stdlib-only."""
    x, y = q
    # NaN compares False against everything, so without this guard a NaN
    # coordinate would fall through every branch below.
    if not (math.isfinite(x) and math.isfinite(y)):
        raise ValueError(f"q={q!r} has a non-finite coordinate")
    if x == 0 or y == 0:
        raise ValueError(f"q={q!r} sits on an axis; section 3 defines no quadrant for it")
    if x > 0 and y < 0:
        return "Q1"
    if x < 0 and y < 0:
        return "Q2"
    if x < 0 and y > 0:
        return "Q3"
    return "Q4"  # x > 0 and y > 0: every other case is excluded above
