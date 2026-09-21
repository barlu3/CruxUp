"""[W4'-1] Survey capture: load + validate one submission against `user_survey`
(0001_init.sql). Fit inputs (width/instep/toe/arch/heel/street size) +
preference inputs (section 7.5) + anchor sets G,B. No images (D4).

House validation style (mirrors catalog/validate.py): `validate(payload) ->
list[str]` accumulates every problem instead of raising on the first one, so
a caller sees the whole submission's issues in one round trip; module
constants mirror the SQL CHECK constraints, with a comment saying so.

Scope of this module: scalar fields and the submission's top-level shape only.
`known_good_shoes` / `known_bad_shoes` are checked here just enough to match
`survey_anchors_array` (each must be a JSON array) -- what is INSIDE each
anchor entry, and whether it resolves to a real shoe, is anchors.py's job
(`resolve_anchors`), which needs a catalog dependency this module deliberately
does not take. store.py composes the two.

D4 (no direct identifiers): `ALLOWED_KEYS` is an allow-list, not a deny-list.
An unrecognised top-level key -- an email address, a name, anything not in the
schema -- is rejected outright rather than silently dropped or passed through,
so it can never ride along into storage. Anchor entries get the same
allow-list treatment independently, in anchors.py.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# --------------------------------------------------------------------------
# Vocabularies
# --------------------------------------------------------------------------

# Mirrors the CHECK constraints in 0001_init.sql: survey_width_valid,
# survey_instep_valid, survey_toe_valid, survey_arch_valid, survey_disc_valid.
# If these drift apart, the insert fails at the database instead of here,
# which is a worse place to discover it -- see test_survey.py, which parses
# the CHECK constraints back out of the migration and asserts equality.
ENUMS: dict[str, set[str]] = {
    "foot_width": {"narrow", "medium", "wide"},
    "instep":     {"low", "medium", "high"},
    "toe_shape":  {"egyptian", "greek", "roman"},
    "arch":       {"low", "medium", "high"},
    "discipline": {"boulder", "sport", "trad", "gym"},
}

# heel_fit, terrain and level have NO matching CHECK constraint in
# 0001_init.sql -- confirmed by grep, and pinned by test_survey.py so this
# comment cannot go stale silently. This is a KNOWN DRIFT, tracked here for a
# follow-up migration; do not "fix" it by editing the SQL from this card (out
# of scope: this stage is read-only on every .sql file). Vocabularies:
#   heel_fit: not modelled in timeline.md; narrow/medium/wide mirrors foot_width.
#   terrain:  timeline.md section 7.5 (slab/vertical/overhang/crack).
#   level:    timeline.md section 7.5 ("experience level"); no fixed vocabulary
#             given there, so beginner/intermediate/advanced/elite is a
#             judgement call, chosen to be the smallest ordered scale that
#             separates a first-time gym climber from a redpoint-grade trad
#             leader for the section 7.5 target-quadrant mapping.
PY_ONLY_ENUMS: dict[str, set[str]] = {
    "heel_fit": {"narrow", "medium", "wide"},
    "terrain":  {"slab", "vertical", "overhang", "crack"},
    "level":    {"beginner", "intermediate", "advanced", "elite"},
}

# NUMERIC(4,1) in 0001_init.sql: 4 significant digits, 1 after the decimal
# point, so the column itself allows |value| < 1000. No real street shoe size
# approaches that, so a tighter plausibility band is enforced too (judgement
# call -- neither 0001_init.sql nor timeline.md names one): 0 excludes "no
# size" smuggled in as a number, 20 comfortably covers the largest listed
# street size in any brand/gender numbering.
STREET_SIZE_NUMERIC_LIMIT = 1000
STREET_SIZE_DECIMALS = 1
STREET_SIZE_MIN, STREET_SIZE_MAX = 0, 20

# Mirrors survey_target_x / survey_target_y: the quadrant plane is [-1, 1]
# (timeline.md section 3).
GOAL_TARGET_MIN, GOAL_TARGET_MAX = -1, 1
GOAL_TARGET_DECIMALS = 3  # NUMERIC(4,3)

# NUMERIC(7,2) in 0001_init.sql: |value| < 100000. The SQL does not floor
# budget_cap_usd at 0; a non-positive cap is rejected here as a judgement call
# -- it would make every shoe fail the section 7.6 budget gate, which is a
# submission error worth catching now rather than a silently empty result set.
BUDGET_MIN_EXCLUSIVE = 0
BUDGET_NUMERIC_LIMIT = 100_000
BUDGET_DECIMALS = 2  # NUMERIC(7,2)

# Scalar `user_survey` columns this module accepts directly from a submission
# (everything except id, survey_token, created_at -- server-assigned -- and
# the two anchor columns, validated separately below).
SCALAR_FIELDS = (
    "foot_width", "instep", "toe_shape", "arch", "heel_fit", "street_size",
    "discipline", "terrain", "level",
    "goal_x_target", "goal_y_target", "budget_cap_usd",
)
ANCHOR_FIELDS = ("known_good_shoes", "known_bad_shoes")

# Every anchor entry costs at least one catalog round trip to resolve
# (anchors.PostgresCatalog), so an unbounded list turns one submission into
# unbounded database work while holding a connection open. A real user names a
# handful of shoes they have owned; 50 across BOTH lists is already far beyond
# that. Checked here, in the shape pass, so store.main() can reject an
# oversized submission before it ever opens a connection.
MAX_ANCHORS_TOTAL = 50
ALLOWED_KEYS = frozenset(SCALAR_FIELDS + ANCHOR_FIELDS)


def _is_number(v: object) -> bool:
    """True for int/float, explicitly False for bool.

    bool is an int subclass in Python (isinstance(True, int) is True), so a
    naive isinstance(v, (int, float)) lets a boolean silently pass as a
    number. catalog/validate.py already carries this exact guard for
    quadrant_x_prior / quadrant_y_prior / msrp_usd; it applies here too.
    """
    return isinstance(v, (int, float)) and not isinstance(v, bool)


# Postgres does NOT reject a value that exceeds a NUMERIC column's scale -- it
# silently ROUNDS it ('0.1234'::numeric(4,3) -> 0.123, '123.456'::numeric(7,2)
# -> 123.46). A submission that validated clean would then be stored as a
# different number, with no error raised anywhere, so the scale is enforced
# here rather than left to the column.
#
# The comparison carries a tolerance on purpose. goal_x_target / goal_y_target
# are computed upstream (section 7.5 derives q* from preference answers), so
# binary-float noise -- 0.1 + 0.2 == 0.30000000000000004 -- is expected and
# must NOT be rejected. Only precision the caller actually meant, which is
# orders of magnitude above that noise floor, is an error.
SCALE_TOLERANCE = 1e-9


def _scale_error(field: str, v: float, decimals: int) -> str | None:
    """Return an error if `v` carries more decimal places than the column can
    store, else None. Tolerance-based -- see SCALE_TOLERANCE."""
    if abs(round(v, decimals) - v) > SCALE_TOLERANCE:
        plural = "" if decimals == 1 else "s"
        return (
            f"{field} {v} must have at most {decimals} decimal place{plural} "
            f"(Postgres would silently round it)"
        )
    return None


# --------------------------------------------------------------------------
# Field checks -- each returns a list so callers can `errors.extend(...)`
# --------------------------------------------------------------------------

def _check_enum(payload: dict, field: str, allowed: set[str]) -> list[str]:
    if payload.get(field) is None:
        return []
    val = payload[field]
    if not isinstance(val, str):
        return [f"{field} must be a string, got {type(val).__name__}"]
    if val not in allowed:
        return [f"{field}={val!r} not in {sorted(allowed)}"]
    return []


def _check_street_size(payload: dict) -> list[str]:
    if payload.get("street_size") is None:
        return []
    v = payload["street_size"]
    if not _is_number(v):
        return [f"street_size must be a number, got {type(v).__name__}"]
    if abs(v) >= STREET_SIZE_NUMERIC_LIMIT:
        return [
            f"street_size {v} does not fit NUMERIC(4,1): |value| must be < "
            f"{STREET_SIZE_NUMERIC_LIMIT}"
        ]
    scale = _scale_error("street_size", v, STREET_SIZE_DECIMALS)
    if scale:
        return [scale]
    if not (STREET_SIZE_MIN < v <= STREET_SIZE_MAX):
        return [
            f"street_size {v} is outside the plausible range "
            f"({STREET_SIZE_MIN}, {STREET_SIZE_MAX}]"
        ]
    return []


def _check_goal(payload: dict, field: str) -> list[str]:
    if payload.get(field) is None:
        return []
    v = payload[field]
    if not _is_number(v):
        return [f"{field} must be a number, got {type(v).__name__}"]
    if not (GOAL_TARGET_MIN <= v <= GOAL_TARGET_MAX):
        return [
            f"{field}={v} outside [{GOAL_TARGET_MIN}, {GOAL_TARGET_MAX}] "
            f"(mirrors survey_target_x / survey_target_y)"
        ]
    scale = _scale_error(field, v, GOAL_TARGET_DECIMALS)
    if scale:
        return [scale]
    return []


def _check_budget(payload: dict) -> list[str]:
    if payload.get("budget_cap_usd") is None:
        return []
    v = payload["budget_cap_usd"]
    if not _is_number(v):
        return [f"budget_cap_usd must be a number, got {type(v).__name__}"]
    if not (BUDGET_MIN_EXCLUSIVE < v < BUDGET_NUMERIC_LIMIT):
        return [
            f"budget_cap_usd {v} must be > {BUDGET_MIN_EXCLUSIVE} and fit "
            f"NUMERIC(7,2) (< {BUDGET_NUMERIC_LIMIT})"
        ]
    scale = _scale_error("budget_cap_usd", v, BUDGET_DECIMALS)
    if scale:
        return [scale]
    return []


def validate(payload: object) -> list[str]:
    """Return a list of error strings for one survey submission. Empty means
    the scalar fields and top-level shape are sound.

    Does NOT resolve known_good_shoes / known_bad_shoes against a catalog --
    see the module docstring. It only checks that each, if present, is a
    JSON array (mirrors survey_anchors_array's `jsonb_typeof(...) = 'array'`).
    """
    if not isinstance(payload, dict):
        return [f"payload must be a mapping, got {type(payload).__name__}"]

    errors: list[str] = []

    extra = set(payload) - ALLOWED_KEYS
    if extra:
        errors.append(
            f"unknown key(s) {sorted(extra)}: D4 allows derived values only -- "
            f"an identifier (e.g. email, name) must never reach storage"
        )

    for field, allowed in ENUMS.items():
        errors.extend(_check_enum(payload, field, allowed))
    for field, allowed in PY_ONLY_ENUMS.items():
        errors.extend(_check_enum(payload, field, allowed))

    errors.extend(_check_street_size(payload))
    errors.extend(_check_goal(payload, "goal_x_target"))
    errors.extend(_check_goal(payload, "goal_y_target"))
    errors.extend(_check_budget(payload))

    for field in ANCHOR_FIELDS:
        if field in payload and not isinstance(payload[field], list):
            errors.append(
                f"{field} must be a list, got {type(payload[field]).__name__} "
                f"(mirrors survey_anchors_array)"
            )

    total_anchors = sum(
        len(payload[f]) for f in ANCHOR_FIELDS
        if isinstance(payload.get(f), list)
    )
    if total_anchors > MAX_ANCHORS_TOTAL:
        errors.append(
            f"{total_anchors} anchors across known_good_shoes + known_bad_shoes "
            f"exceeds the maximum of {MAX_ANCHORS_TOTAL}"
        )

    return errors


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Validate a survey submission's scalar fields and shape (W4'-1)"
    )
    ap.add_argument("payload", type=Path, help="path to a JSON survey submission")
    args = ap.parse_args()

    try:
        payload = json.loads(args.payload.read_text())
    # RecursionError: json.loads blows the stack on deeply nested input
    # (~100k opening brackets) and RecursionError is NOT a JSONDecodeError,
    # so without it here a crafted payload exits with a traceback instead of
    # a clean error.
    except (OSError, json.JSONDecodeError, RecursionError) as exc:
        print(f"error: cannot read payload: {exc}", file=sys.stderr)
        return 1

    errors = validate(payload)
    if errors:
        print(f"\n{len(errors)} ERROR(S):")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("\nsubmission shape valid (anchors not yet resolved against a catalog; see store.py)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
