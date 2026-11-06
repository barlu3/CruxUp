"""[W7-2-D] Tests for score.py: the combined ranking (timeline.md section 7.6).

Shoes are hand-made dicts so each gate and term is exercised in isolation.
Expected totals are computed from scorer_config weights, not typed in.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "recommend"))
import score as S  # noqa: E402
import scorer_config as C  # noqa: E402


def shoe(sid="s1", brand="Brand", model="Model", price=100, x=0.5, y=-0.5, **over):
    row = {
        "id": sid, "brand": brand, "model": model, "version": "", "gender": "unisex",
        "status": "active", "last_shape": "asymmetric", "downturn": "aggressive",
        "closure": "velcro", "msrp_usd": price,
        "quadrant_x_prior": x, "quadrant_y_prior": y, "prior_source": "hand",
    }
    row.update(over)
    return row


def run(survey, shoes, size_rows=()):
    return S.recommend(survey, shoes, list(size_rows))


def by_id(ranking, sid):
    return next(r for r in ranking.results if r["id"] == sid)


def ids(ranking):
    return [r["id"] for r in ranking.results]


# --- price gate -----------------------------------------------------------

def test_over_cap_shoe_is_excluded():
    ranking = run({"budget_cap_usd": 100}, [shoe(price=101)])
    assert ids(ranking) == []


def test_over_cap_shoe_counts_as_over_budget():
    ranking = run({"budget_cap_usd": 100}, [shoe(price=101)])
    assert ranking.gated_out["over_budget"] == 1


def test_shoe_priced_exactly_at_cap_is_kept():
    ranking = run({"budget_cap_usd": 100}, [shoe(price=100)])
    assert ids(ranking) == ["s1"]


def test_null_price_shoe_is_kept_under_a_cap():
    ranking = run({"budget_cap_usd": 100}, [shoe(price=None)])
    assert ids(ranking) == ["s1"]


def test_null_price_shoe_is_flagged_price_unknown():
    ranking = run({"budget_cap_usd": 100}, [shoe(price=None)])
    assert by_id(ranking, "s1")["price_unknown"] is True


def test_known_price_shoe_is_not_flagged_price_unknown():
    ranking = run({"budget_cap_usd": 100}, [shoe(price=50)])
    assert by_id(ranking, "s1")["price_unknown"] is False


def test_null_price_budget_score_is_neutral():
    ranking = run({"budget_cap_usd": 100}, [shoe(price=None)])
    assert by_id(ranking, "s1")["budget_score"] == C.BUDGET_UNKNOWN_PRICE


def test_null_price_is_still_flagged_without_a_cap():
    ranking = run({}, [shoe(price=None)])
    assert by_id(ranking, "s1")["price_unknown"] is True


def test_budget_score_at_cap_is_half():
    ranking = run({"budget_cap_usd": 100}, [shoe(price=100)])
    assert by_id(ranking, "s1")["budget_score"] == 0.5


def test_free_shoe_budget_score_is_one():
    ranking = run({"budget_cap_usd": 100}, [shoe(price=0)])
    assert by_id(ranking, "s1")["budget_score"] == 1.0


def test_budget_score_is_none_without_a_cap():
    ranking = run({}, [shoe()])
    assert by_id(ranking, "s1")["budget_score"] is None


def test_budget_term_is_reported_included_with_a_cap():
    ranking = run({"budget_cap_usd": 100}, [shoe()])
    assert ranking.terms["budget"] is True


# --- term exclusion and renormalisation -----------------------------------

def test_no_cap_total_renormalises_over_fit_and_style():
    survey = {"toe_shape": "egyptian", "goal_x_target": 0.5, "goal_y_target": -0.5}
    ranking = run(survey, [shoe(x=0.5, y=-0.5)])
    expected = (C.ALPHA * 1.0 + C.BETA * 1.0) / (C.ALPHA + C.BETA)
    assert by_id(ranking, "s1")["total_score"] == pytest.approx(expected, abs=1e-4)


def test_cap_only_survey_total_equals_budget_score():
    ranking = run({"budget_cap_usd": 100}, [shoe(price=50)])
    assert by_id(ranking, "s1")["total_score"] == 0.75


def test_fit_term_excluded_without_any_fit_input():
    ranking = run({"goal_x_target": 0.5, "goal_y_target": -0.5}, [shoe()])
    assert ranking.terms["fit"] is False


def test_fit_score_is_none_when_fit_term_excluded():
    ranking = run({"goal_x_target": 0.5, "goal_y_target": -0.5}, [shoe()])
    assert by_id(ranking, "s1")["fit_score"] is None


def test_style_term_excluded_without_target():
    ranking = run({"toe_shape": "egyptian"}, [shoe()])
    assert ranking.terms["style"] is False


def test_target_is_none_without_discipline():
    ranking = run({"toe_shape": "egyptian"}, [shoe()])
    assert ranking.target is None


def test_fit_term_included_by_anchors_alone():
    survey = {"known_good_shoes": [{"shoe_id": "s1"}]}
    ranking = run(survey, [shoe()])
    assert ranking.terms["fit"] is True


def test_stored_target_is_reported():
    ranking = run({"goal_x_target": 0.25, "goal_y_target": -0.5}, [shoe()])
    assert ranking.target == (0.25, -0.5)


def test_empty_survey_totals_are_neutral():
    ranking = run({}, [shoe("a"), shoe("b", model="Other")])
    assert [r["total_score"] for r in ranking.results] == [0.5, 0.5]


def test_empty_survey_warns_no_scoring_inputs():
    ranking = run({}, [shoe()])
    assert "no_scoring_inputs" in ranking.warnings


def test_survey_with_inputs_does_not_warn_no_scoring_inputs():
    ranking = run({"toe_shape": "greek"}, [shoe()])
    assert "no_scoring_inputs" not in ranking.warnings


def test_survey_warnings_are_deduplicated_in_order():
    ranking = run({}, [shoe()])
    assert ranking.warnings == ("no_target", "no_scoring_inputs")


# --- size gate ------------------------------------------------------------

def row(sid, size, exists):
    return {"shoe_id": sid, "us_street_equiv": size, "size_exists": exists}


def test_size_exists_false_row_excludes_the_shoe():
    ranking = run({"street_size": 9.5}, [shoe()], [row("s1", 9.5, False)])
    assert ids(ranking) == []


def test_size_exists_false_row_counts_as_size_unavailable():
    ranking = run({"street_size": 9.5}, [shoe()], [row("s1", 9.5, False)])
    assert ranking.gated_out["size_unavailable"] == 1


def test_size_exists_true_row_keeps_the_shoe():
    ranking = run({"street_size": 9.5}, [shoe()], [row("s1", 9.5, True)])
    assert ids(ranking) == ["s1"]


def test_row_for_another_size_keeps_the_shoe():
    ranking = run({"street_size": 9.5}, [shoe()], [row("s1", 10.0, False)])
    assert ids(ranking) == ["s1"]


def test_row_for_another_shoe_keeps_the_shoe():
    ranking = run({"street_size": 9.5}, [shoe()], [row("other", 9.5, False)])
    assert ids(ranking) == ["s1"]


def test_missing_size_rows_keep_the_shoe():
    ranking = run({"street_size": 9.5}, [shoe()], [])
    assert ids(ranking) == ["s1"]


def test_no_street_size_keeps_the_shoe():
    ranking = run({}, [shoe()], [row("s1", 9.5, False)])
    assert ids(ranking) == ["s1"]


def test_is_size_available_is_false_only_for_a_matching_false_row():
    assert S.is_size_available("s1", 9.5, [row("s1", 9.5, False)]) is False


# --- candidates -----------------------------------------------------------

def test_inactive_shoe_is_excluded():
    ranking = run({}, [shoe(status="discontinued")])
    assert ids(ranking) == []


def test_inactive_shoe_is_not_counted_as_unplaced():
    ranking = run({}, [shoe(status="discontinued", x=None, y=None, prior_source=None)])
    assert ranking.gated_out["unplaced"] == 0


def test_active_shoe_without_prior_is_excluded():
    ranking = run({}, [shoe(x=None, y=None, prior_source=None)])
    assert ids(ranking) == []


def test_active_shoe_without_prior_counts_as_unplaced():
    ranking = run({}, [shoe(x=None, y=None, prior_source=None)])
    assert ranking.gated_out["unplaced"] == 1


def test_on_axis_prior_raises():
    with pytest.raises(ValueError):
        run({}, [shoe(x=0.0, y=-0.5)])


def test_unknown_prior_source_raises_scoring_error():
    with pytest.raises(C.ScoringError):
        run({}, [shoe(prior_source="mystery")])


# --- ranking order --------------------------------------------------------

def three_shoes():
    return [shoe("c", "Zed", "Z"), shoe("a", "Alpha", "A"), shoe("b", "Beta", "B")]


def test_ranks_are_contiguous_from_one():
    ranking = run({}, three_shoes())
    assert [r["rank"] for r in ranking.results] == [1, 2, 3]


def test_tied_totals_are_ordered_by_brand():
    ranking = run({}, three_shoes())
    assert ids(ranking) == ["a", "b", "c"]


def test_tie_break_is_case_insensitive_on_brand():
    ranking = run({}, [shoe("u", "alpha", "M"), shoe("l", "Beta", "M")])
    assert ids(ranking) == ["u", "l"]


def test_tie_break_falls_through_to_id():
    ranking = run({}, [shoe("z"), shoe("y")])
    assert ids(ranking) == ["y", "z"]


def test_output_is_independent_of_input_order():
    first = run({}, three_shoes())
    second = run({}, list(reversed(three_shoes())))
    assert ids(first) == ids(second)


def test_same_input_gives_identical_output_twice():
    survey = {"toe_shape": "greek", "goal_x_target": 0.1, "goal_y_target": -0.3}
    assert run(survey, three_shoes()) == run(survey, three_shoes())


def test_higher_total_ranks_first():
    survey = {"goal_x_target": 0.9, "goal_y_target": -0.9}
    near, far = shoe("near", "Zed", x=0.9, y=-0.9), shoe("far", "Alpha", x=-0.9, y=0.9)
    assert ids(run(survey, [far, near])) == ["near", "far"]


def test_equal_totals_prefer_higher_fit():
    # Style compensates the fit gap exactly: a 0.4 fit gap costs
    # ALPHA*0.4 = BETA*0.45, and 0.45 of style is 0.45*2*sqrt(2) of distance.
    survey = {"toe_shape": "egyptian", "goal_x_target": 0.5, "goal_y_target": -0.5}
    high_fit = shoe("hi", "Zed", x=-0.77279, y=-0.5, last_shape="asymmetric")
    low_fit = shoe("lo", "Alpha", x=0.5, y=-0.5, last_shape="neutral")
    assert ids(run(survey, [low_fit, high_fit])) == ["hi", "lo"]


def test_scores_are_rounded_to_four_places():
    survey = {"goal_x_target": 0.123, "goal_y_target": -0.321, "toe_shape": "roman",
              "budget_cap_usd": 97}
    result = run(survey, [shoe(price=33, x=0.3337, y=-0.7771)]).results[0]
    scores = [result[k] for k in ("fit_score", "style_score", "budget_score", "total_score")]
    assert all(round(v, 4) == v for v in scores)


def test_rounding_happens_before_ranking():
    # Two shoes whose style differs below 4 dp must tie on total and fall to
    # the name tie-break, not to the sub-resolution difference.
    survey = {"goal_x_target": 0.5, "goal_y_target": -0.5}
    a = shoe("a", "Zed", x=0.5, y=-0.5)
    b = shoe("b", "Alpha", x=0.50001, y=-0.5)
    assert ids(run(survey, [a, b])) == ["b", "a"]


# --- results content ------------------------------------------------------

def test_result_carries_identity_fields():
    result = run({}, [shoe(brand="Acme", model="Rocket")]).results[0]
    assert (result["brand"], result["model"], result["version"], result["gender"]) == (
        "Acme", "Rocket", "", "unisex")


def test_result_msrp_is_a_float():
    from decimal import Decimal
    result = run({}, [shoe(price=Decimal("129.00"))]).results[0]
    assert result["msrp_usd"] == 129.0


def test_result_quadrant_comes_from_the_prior():
    assert run({}, [shoe(x=0.5, y=-0.5)]).results[0]["quadrant"] == "Q1"


def test_section_three_anchor_is_flagged():
    solution = shoe(brand="La Sportiva", model="Solution")
    assert run({}, [solution]).results[0]["is_anchor"] is True


def test_non_anchor_is_not_flagged():
    assert run({}, [shoe()]).results[0]["is_anchor"] is False


def test_result_has_confidence_label():
    assert run({}, [shoe()]).results[0]["confidence_label"] == "low"


def test_scorer_version_is_reported():
    assert run({}, []).scorer_version == C.SCORER_VERSION


# --- anchors --------------------------------------------------------------

def test_bad_fit_shoe_is_ranked_not_hidden():
    survey = {"known_bad_shoes": [{"shoe_id": "s1"}]}
    assert ids(run(survey, [shoe()])) == ["s1"]


def test_bad_fit_shoe_carries_reported_poor_fit_warning():
    survey = {"known_bad_shoes": [{"shoe_id": "s1"}]}
    assert "reported_poor_fit" in by_id(run(survey, [shoe()]), "s1")["warnings"]


def test_good_fit_shoe_carries_reported_good_fit_warning():
    survey = {"known_good_shoes": [{"shoe_id": "s1"}]}
    assert "reported_good_fit" in by_id(run(survey, [shoe()]), "s1")["warnings"]


def test_good_fit_shoe_scores_full_fit():
    survey = {"known_good_shoes": [{"shoe_id": "s1"}]}
    assert by_id(run(survey, [shoe()]), "s1")["fit_score"] == 1.0


def test_anchor_missing_from_catalog_warns_at_survey_level():
    survey = {"known_good_shoes": [{"shoe_id": "gone"}]}
    assert "anchor_not_in_catalog:1" in run(survey, [shoe()]).warnings


def test_anchor_missing_from_catalog_leaves_fit_term_excluded():
    survey = {"known_good_shoes": [{"shoe_id": "gone"}]}
    assert run(survey, [shoe()]).terms["fit"] is False


def test_unplaced_anchor_shoe_still_defines_fit_family():
    unplaced = shoe("u", x=None, y=None, prior_source=None, last_shape="neutral", downturn="flat")
    survey = {"known_good_shoes": [{"shoe_id": "u"}]}
    ranking = run(survey, [unplaced, shoe("s1")])
    assert by_id(ranking, "s1")["fit_score"] == 0.0


def test_per_shoe_warnings_are_deduplicated():
    survey = {"known_good_shoes": [{"shoe_id": "s1"}], "toe_shape": "greek"}
    warnings = by_id(run(survey, [shoe(last_shape=None)]), "s1")["warnings"]
    assert warnings.count("catalog_field_missing:last_shape") == 1


# --- read-only output -------------------------------------------------------

def test_ranking_results_are_a_tuple():
    assert isinstance(run({}, [shoe()]).results, tuple)


def test_ranking_warnings_are_a_tuple():
    assert isinstance(run({}, [shoe()]).warnings, tuple)


def test_ranking_terms_cannot_be_mutated():
    with pytest.raises(TypeError):
        run({}, [shoe()]).terms["fit"] = True


def test_ranking_gated_out_cannot_be_mutated():
    with pytest.raises(TypeError):
        run({}, [shoe()]).gated_out["unplaced"] = 9


def test_result_cannot_be_mutated():
    with pytest.raises(TypeError):
        run({}, [shoe()]).results[0]["rank"] = 9


def test_result_warnings_are_a_tuple():
    assert isinstance(run({}, [shoe()]).results[0]["warnings"], tuple)


# --- cap validation ----------------------------------------------------------

def test_zero_cap_raises():
    with pytest.raises(ValueError):
        run({"budget_cap_usd": 0}, [shoe()])


def test_negative_cap_raises():
    with pytest.raises(ValueError):
        run({"budget_cap_usd": -5}, [shoe()])


# --- size matching -----------------------------------------------------------

def test_size_match_tolerates_float_noise():
    assert S.is_size_available("s1", 9.0 + 0.1 + 0.2, [row("s1", 9.3, False)]) is False


# --- literal renormalisation --------------------------------------------------

def test_fit_and_budget_only_total_is_renormalised_literal():
    # (0.45 * 1.0 + 0.15 * 0.5) / (0.45 + 0.15) = 0.525 / 0.6
    survey = {"toe_shape": "egyptian", "budget_cap_usd": 100}
    assert by_id(run(survey, [shoe(price=100)]), "s1")["total_score"] == 0.875
