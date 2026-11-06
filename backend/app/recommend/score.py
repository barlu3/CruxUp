"""[W7-2-D] Combined rank (timeline.md section 7.6):
Score = (alpha*Fit + beta*Style + gamma*Budget), behind a size gate and a
price gate. Pure: the caller loads the survey row, the shoes and the
shoe_size_map rows; nothing here does IO.

Candidates are shoes with status 'active' and a quadrant prior. Inactive
shoes are silently excluded (they are not a "gated out" outcome the user can
act on); active shoes without a prior are counted in gated_out.unplaced.

Gates, applied in this order, each shoe counted once at the first that drops it:
  size   D9: only a shoe_size_map row for the user's street size with
         size_exists FALSE excludes. No street size, no rows, or no matching
         row all keep the shoe.
  price  price > cap excludes. A NULL msrp is never gated (the cap cannot be
         evaluated) and never silently treated as in-budget: price_unknown is
         set on the result and the budget score is the neutral
         BUDGET_UNKNOWN_PRICE (timeline.md section 13, null-price rule).

Terms: a term with no input for the whole survey (no target; no fit answers
and no resolved anchors; no cap) is dropped and the remaining weights are
renormalised, so a missing input is neutral rather than a zero. Its score is
None on every result. If all three are dropped every total is 0.5.

Every score is rounded to 4 dp BEFORE ranking, so the tie-break decides
differences below the displayed resolution rather than float noise. Order:
total desc, fit desc (None last), then lower(brand), lower(model), version,
gender, id. ScoringError and ValueError propagate: they mean a corrupt row or
a model gap, not a user-facing condition.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[0] / "catalog"))
import confidence as conf  # noqa: E402
import fit as fit_mod  # noqa: E402
import priors  # noqa: E402
import scorer_config as config  # noqa: E402
import style  # noqa: E402
from validate import ANCHORS  # noqa: E402

SCORE_DECIMALS = 4
NEUTRAL_TOTAL = 0.5


@dataclass(frozen=True)
class Ranking:
    scorer_version: str
    target: tuple[float, float] | None
    terms: Mapping[str, bool]
    gated_out: Mapping[str, int]
    warnings: tuple[str, ...]
    results: tuple[Mapping[str, Any], ...]


def recommend(
    survey: Mapping[str, Any],
    shoes: Iterable[Mapping[str, Any]],
    size_rows: Sequence[Mapping[str, Any]],
) -> Ranking:
    shoes = list(shoes)
    target, warnings = style.resolve_target(survey)
    good_entries = survey.get("known_good_shoes") or []
    bad_entries = survey.get("known_bad_shoes") or []
    shoes_by_id = {s["id"]: s for s in shoes}
    good, good_warnings = fit_mod.anchor_families(good_entries, shoes_by_id)
    bad, bad_warnings = fit_mod.anchor_families(bad_entries, shoes_by_id)
    warnings = warnings + good_warnings + bad_warnings
    has_anchors = bool(good or bad)
    cap = _to_float(survey.get("budget_cap_usd"))
    # The schema already rejects a non-positive cap at the API, but recommend
    # is public and 1 - price/(2*cap) divides by it.
    if cap is not None and cap <= 0:
        raise ValueError(f"budget_cap_usd={cap} must be > 0")
    terms = {
        "fit": has_anchors or any(survey.get(q) is not None for q in conf.FIT_QUESTIONS),
        "style": target is not None,
        "budget": cap is not None,
    }
    weights = {name: w for name, w in (
        ("fit", config.ALPHA), ("style", config.BETA), ("budget", config.GAMMA)) if terms[name]}
    if not weights:
        warnings.append("no_scoring_inputs")

    good_ids = {e["shoe_id"] for e in good_entries}
    bad_ids = {e["shoe_id"] for e in bad_entries}
    survey_conf = conf.c_survey(survey, has_anchors)
    street_size = _to_float(survey.get("street_size"))
    unavailable = _unavailable_sizes(size_rows)
    gated_out = {"over_budget": 0, "size_unavailable": 0, "unplaced": 0}
    results = []
    for shoe in shoes:
        if shoe["status"] != "active":
            continue
        if shoe["quadrant_x_prior"] is None:
            gated_out["unplaced"] += 1
            continue
        if _is_unavailable(shoe["id"], street_size, unavailable):
            gated_out["size_unavailable"] += 1
            continue
        price = _to_float(shoe["msrp_usd"])
        if cap is not None and price is not None and price > cap:
            gated_out["over_budget"] += 1
            continue
        results.append(_score_shoe(
            shoe, survey, target, cap, price, weights, good, bad,
            survey_conf, good_ids, bad_ids))

    results.sort(key=_sort_key)
    for rank, result in enumerate(results, start=1):
        result["rank"] = rank
    return Ranking(
        scorer_version=config.SCORER_VERSION,
        target=target,
        terms=MappingProxyType(terms),
        gated_out=MappingProxyType(gated_out),
        warnings=tuple(_dedupe(warnings)),
        results=tuple(MappingProxyType(r) for r in results),
    )


def is_size_available(
    shoe_id: str, street_size: float | None, size_rows: Iterable[Mapping[str, Any]]
) -> bool:
    """D9: False only when a row for this shoe and street size says the brand
    does not make it."""
    return not _is_unavailable(shoe_id, street_size, _unavailable_sizes(size_rows))


def _unavailable_sizes(size_rows: Iterable[Mapping[str, Any]]) -> set[tuple[str, float]]:
    return {
        (r["shoe_id"], _size_key(r["us_street_equiv"]))
        for r in size_rows
        if r["size_exists"] is False and r["us_street_equiv"] is not None
    }


def _is_unavailable(
    shoe_id: str, street_size: float | None, unavailable: set[tuple[str, float]]
) -> bool:
    return street_size is not None and (shoe_id, _size_key(street_size)) in unavailable


# NUMERIC(4,1) sizes: compare at the column's scale, not by float equality.
def _size_key(size: Any) -> float:
    return round(float(size), 1)


def _score_shoe(shoe, survey, target, cap, price, weights, good, bad,
                survey_conf, good_ids, bad_ids) -> dict[str, Any]:
    x, y = float(shoe["quadrant_x_prior"]), float(shoe["quadrant_y_prior"])
    quadrant = priors.quadrant(x, y)
    if quadrant == "ON-AXIS":
        raise ValueError(f"shoe {shoe['id']} has an on-axis prior ({x}, {y})")

    warnings: list[str] = []
    fit_value = style_value = budget_value = None
    if "fit" in weights:
        cat, cat_warnings = fit_mod.fit_cat(survey, shoe)
        anchor, anchor_warnings = fit_mod.fit_anchor(shoe, good, bad)
        warnings += cat_warnings + anchor_warnings
        fit_value = fit_mod.fit_score(cat, anchor)
    if "style" in weights:
        style_value = style.style_score((x, y), target)
    if "budget" in weights:
        budget_value = (config.BUDGET_UNKNOWN_PRICE if price is None
                        else 1 - price / (2 * cap))

    parts = {"fit": fit_value, "style": style_value, "budget": budget_value}
    if weights:
        total = sum(w * parts[name] for name, w in weights.items()) / sum(weights.values())
    else:
        total = NEUTRAL_TOTAL

    if shoe["id"] in good_ids:
        warnings.append("reported_good_fit")
    if shoe["id"] in bad_ids:
        warnings.append("reported_poor_fit")

    c = conf.confidence(survey_conf, conf.c_place(shoe["prior_source"]), target is not None)
    return {
        "id": shoe["id"],
        "brand": shoe["brand"],
        "model": shoe["model"],
        "version": shoe["version"],
        "gender": shoe["gender"],
        "x": x,
        "y": y,
        "quadrant": quadrant,
        "prior_source": shoe["prior_source"],
        "is_anchor": (shoe["brand"], shoe["model"], shoe["version"]) in ANCHORS,
        "msrp_usd": price,
        "price_unknown": price is None,
        "fit_score": _round(fit_value),
        "style_score": _round(style_value),
        "budget_score": _round(budget_value),
        "total_score": _round(total),
        "confidence": _round(c),
        "confidence_label": conf.label(c),
        "warnings": tuple(_dedupe(warnings)),
    }


def _sort_key(result: Mapping[str, Any]) -> tuple:
    fit_value = result["fit_score"]
    return (
        -result["total_score"],
        fit_value is None,
        -(fit_value or 0.0),
        result["brand"].lower(),
        result["model"].lower(),
        result["version"],
        result["gender"],
        result["id"],
    )


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, SCORE_DECIMALS)


def _to_float(value: Any) -> float | None:
    # Decimal from psycopg NUMERIC columns.
    return None if value is None else float(value)


def _dedupe(items: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(items))
