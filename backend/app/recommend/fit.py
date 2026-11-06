"""[W7-2-B] Survey-derived fit (timeline.md section 7.2):
Fit = lambda * Fit_anchor + (1 - lambda) * Fit_cat.

The Fit_cat tables (scorer_config.py) are a DOMAIN JUDGEMENT pending climber
sign-off (W4'-3), not measurements.

arch and heel_fit are collected by the survey but deliberately unused: the
catalog has no field to match them against, and a score term with nothing to
compare would be noise.

A missing part is never scored as 0: Fit_cat averages only the questions the
user answered, and fit_score uses whichever of anchor/cat exists. None means
"no fit signal at all", which the caller must treat differently from "bad fit".

Warnings: fit_cat, fit_anchor and anchor_families return (value, warnings).
Warnings are plain strings that go to the client, so they carry a count or a
field name but never a shoe id. A NULL catalog field is scored neutral and
emits "catalog_field_missing:<field>"; anchors missing from the catalog emit
"anchor_not_in_catalog:<count>". Callers merge and dedupe the lists.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scorer_config as config  # noqa: E402
from scorer_config import ScoringError  # noqa: E402

Family = tuple[str | None, str | None]  # (last_shape, downturn)


def fit_cat(survey: Mapping[str, Any], shoe: Mapping[str, Any]) -> tuple[float | None, list[str]]:
    """Mean of the sub-scores for the fit questions the user answered."""
    scores: list[float] = []
    warnings: list[str] = []
    if survey.get("toe_shape") is not None:
        scores.append(_last_sub_score(
            config.FIT_TOE_BY_LAST, "toe_shape", survey["toe_shape"], shoe, warnings))
    if survey.get("foot_width") is not None:
        scores.append(_last_sub_score(
            config.FIT_WIDTH_BY_LAST, "foot_width", survey["foot_width"], shoe, warnings))
    if survey.get("instep") is not None:
        scores.append(_instep_sub_score(survey["instep"], shoe, warnings))
    return (sum(scores) / len(scores) if scores else None), warnings


def anchor_similarity(a: Family, b: Family) -> float:
    """1 - (|dlast| + |ddownturn|) / 4. A NULL field counts as
    NULL_STEP_DISTANCE on its dimension: an unknown last must not be mistaken
    for a match, but one ordinal step (half the scale) keeps it from being
    treated as the worst."""
    return 1 - (_distance(a[0], b[0], config.LAST_ORDINAL, "last_shape")
                + _distance(a[1], b[1], config.DOWNTURN_ORDINAL, "downturn")) / 4


def anchor_families(
    anchor_entries: Iterable[Mapping[str, Any]], shoes_by_id: Mapping[str, Mapping[str, Any]]
) -> tuple[list[Family], list[str]]:
    """Look anchors up by shoe_id. An id missing from the catalog (shoe since
    removed) is skipped and counted in one warning, never an error: one stale
    anchor must not take down the whole recommendation."""
    families: list[Family] = []
    warnings: list[str] = []
    missing = 0
    for entry in anchor_entries:
        shoe = shoes_by_id.get(entry["shoe_id"])
        if shoe is None:
            missing += 1
            continue
        _warn_if_null(shoe, ("last_shape", "downturn"), warnings)
        families.append((shoe.get("last_shape"), shoe.get("downturn")))
    if missing:
        warnings.append(f"anchor_not_in_catalog:{missing}")
    return families, warnings


def fit_anchor(
    shoe: Mapping[str, Any], good_families: list[Family], bad_families: list[Family]
) -> tuple[float | None, list[str]]:
    warnings: list[str] = []
    if not good_families and not bad_families:
        return None, warnings
    _warn_if_null(shoe, ("last_shape", "downturn"), warnings)
    family = (shoe.get("last_shape"), shoe.get("downturn"))
    parts = []
    if good_families:
        parts.append(max(anchor_similarity(family, g) for g in good_families))
    if bad_families:
        parts.append(1 - max(anchor_similarity(family, b) for b in bad_families))
    return sum(parts) / len(parts), warnings


def fit_score(cat: float | None, anchor: float | None) -> float | None:
    if cat is not None and anchor is not None:
        return config.LAMBDA_ANCHOR * anchor + (1 - config.LAMBDA_ANCHOR) * cat
    return anchor if anchor is not None else cat


def _warn_if_null(shoe: Mapping[str, Any], fields: Iterable[str], warnings: list[str]) -> None:
    for field in fields:
        warning = f"catalog_field_missing:{field}"
        if shoe.get(field) is None and warning not in warnings:
            warnings.append(warning)


def _check_answer(field: str, answer: Any, allowed: Iterable[str]) -> None:
    # isinstance first: an unhashable answer would otherwise raise TypeError
    # from the membership test instead of a ScoringError.
    if not isinstance(answer, str) or answer not in allowed:
        raise ScoringError(f"{field}={answer!r} not in {sorted(allowed)}")


def _last_sub_score(
    table: Mapping, field: str, answer: Any, shoe: Mapping[str, Any], warnings: list[str]
) -> float:
    _check_answer(field, answer, table)
    last = shoe.get("last_shape")
    if last is None:
        _warn_if_null(shoe, ("last_shape",), warnings)
        return config.UNKNOWN_SUB_SCORE
    return table[answer][_ordinal(last, config.LAST_ORDINAL, "last_shape")]


def _instep_sub_score(answer: Any, shoe: Mapping[str, Any], warnings: list[str]) -> float:
    table = config.FIT_INSTEP_BY_CLOSURE
    _check_answer("instep", answer, table)
    closure = shoe.get("closure")
    if closure is None:
        _warn_if_null(shoe, ("closure",), warnings)
        return config.UNKNOWN_SUB_SCORE
    _check_answer("closure", closure, table[answer])
    return table[answer][closure]


def _distance(a: str | None, b: str | None, ordinals: Mapping[str, int], field: str) -> float:
    if a is None or b is None:
        return config.NULL_STEP_DISTANCE
    return abs(_ordinal(a, ordinals, field) - _ordinal(b, ordinals, field))


def _ordinal(value: str, ordinals: Mapping[str, int], field: str) -> int:
    _check_answer(field, value, ordinals)
    return ordinals[value]
