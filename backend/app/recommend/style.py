"""[W7-2-A] Quadrant proximity (timeline.md section 7.3) and resolution of
the user's target q* from a stored survey row.

Style_j = 1 - ||q_j - q*||_2 / (2*sqrt(2)); 2*sqrt(2) is the diagonal of the
[-1, 1]^2 plane, so Style is in [0, 1].
"""

from __future__ import annotations

import math
import sys
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "survey"))
import preferences  # noqa: E402

_MAX_DISTANCE = 2 * math.sqrt(2)


Point = tuple[float, float]


def style_score(q: Point, q_star: Point) -> float:
    """Section 7.3 proximity in [0, 1]: 1 at the target, 0 at the opposite
    corner of the plane."""
    return 1 - math.dist(q, q_star) / _MAX_DISTANCE


def resolve_target(survey: Mapping[str, Any]) -> tuple[Point | None, list[str]]:
    """Return (q*, warnings) for a stored survey row.

    The stored goal_x_target / goal_y_target win when BOTH are present, and
    are validated, not trusted: each must be a real number (not bool), finite
    and within [-1, 1], else ValueError. The DB CHECKs enforce the range, but
    a corrupt row must fail loudly here rather than yield a silently wrong
    ranking. Nothing is clamped.

    Exactly one NULL is half-corrupt data (the two are always written
    together), so it raises ValueError. Only when BOTH are NULL is the target
    recomputed from discipline/terrain/level with no goal nudge, since the
    slider answer was never given; the warning tells the caller the target is
    approximate. A ValueError from an invalid stored terrain/level is
    likewise not caught.

    discipline is optional in the survey, so (None, ["no_target"]) is a
    legitimate outcome, not an error.
    """
    x, y = survey.get("goal_x_target"), survey.get("goal_y_target")
    if (x is None) != (y is None):
        raise ValueError("goal_x_target and goal_y_target must both be set or both be NULL")
    if x is not None:
        return (_check_target("goal_x_target", x), _check_target("goal_y_target", y)), []
    discipline = survey.get("discipline")
    if discipline is None:
        return None, ["no_target"]
    target = preferences.target_quadrant(
        discipline, survey.get("terrain"), survey.get("level"), None
    )
    return target, ["target_recomputed_without_goal"]


def _check_target(field: str, value: Any) -> float:
    # Decimal: psycopg returns NUMERIC(4,3) columns as Decimal.
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError(f"{field} must be a number, got {type(value).__name__}")
    if not isinstance(value, int) and not math.isfinite(value):
        raise ValueError(f"{field}={value} must be finite")
    if not -1 <= value <= 1:
        raise ValueError(f"{field}={value} outside [-1, 1]")
    return float(value)
