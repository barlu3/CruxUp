"""[W7-2-B] Tests for fit.py: survey-derived fit (timeline.md section 7.2).

Expected values come from the Fit_cat tables in scorer_config.py, which are a
judgement pending climber sign-off (W4'-3); these tests pin the arithmetic
around them, not the folklore.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "recommend"))
import fit as F  # noqa: E402
import scorer_config as C  # noqa: E402

ASYM = {"id": "a", "last_shape": "asymmetric", "downturn": "aggressive", "closure": "velcro"}
NEUTRAL = {"id": "n", "last_shape": "neutral", "downturn": "flat", "closure": "lace"}
SEMI = {"id": "s", "last_shape": "semi-asymmetric", "downturn": "moderate", "closure": "slipper"}


def cat(survey, shoe):
    return F.fit_cat(survey, shoe)[0]


def anchor(shoe, good, bad):
    return F.fit_anchor(shoe, good, bad)[0]


def families(*shoes):
    return [(s["last_shape"], s["downturn"]) for s in shoes]


# --- fit_cat -------------------------------------------------------------

def test_egyptian_toe_on_asymmetric_last_is_one():
    assert cat({"toe_shape": "egyptian"}, ASYM) == 1.0


def test_roman_toe_on_asymmetric_last_is_point_four():
    assert cat({"toe_shape": "roman"}, ASYM) == 0.4


def test_wide_foot_on_neutral_last_is_one():
    assert cat({"foot_width": "wide"}, NEUTRAL) == 1.0


def test_high_instep_in_lace_shoe_is_one():
    assert cat({"instep": "high"}, NEUTRAL) == 1.0


def test_high_instep_in_slipper_is_half():
    assert cat({"instep": "high"}, SEMI) == 0.5


def test_answered_sub_scores_are_averaged():
    survey = {"toe_shape": "roman", "foot_width": "wide"}
    assert cat(survey, ASYM) == pytest.approx((0.4 + 0.4) / 2)


def test_unanswered_fields_are_not_counted_as_zero():
    survey = {"toe_shape": "egyptian", "foot_width": None, "instep": None}
    assert cat(survey, ASYM) == 1.0


def test_no_fit_fields_answered_gives_none():
    assert cat({"arch": "high", "heel_fit": "wide"}, ASYM) is None


def test_null_last_shape_scores_half_on_toe():
    shoe = {**ASYM, "last_shape": None}
    assert cat({"toe_shape": "roman"}, shoe) == 0.5


def test_null_last_shape_scores_half_on_width():
    shoe = {**ASYM, "last_shape": None}
    assert cat({"foot_width": "narrow"}, shoe) == 0.5


def test_null_closure_scores_half_on_instep():
    shoe = {**ASYM, "closure": None}
    assert cat({"instep": "high"}, shoe) == 0.5


def test_unknown_last_shape_raises_scoring_error():
    shoe = {**ASYM, "last_shape": "banana"}
    with pytest.raises(C.ScoringError):
        cat({"toe_shape": "roman"}, shoe)


# --- anchor_similarity ---------------------------------------------------

def test_identical_families_have_similarity_one():
    assert F.anchor_similarity(("asymmetric", "aggressive"), ("asymmetric", "aggressive")) == 1.0


def test_opposite_families_have_similarity_zero():
    assert F.anchor_similarity(("neutral", "flat"), ("asymmetric", "aggressive")) == 0.0


def test_null_last_counts_as_distance_one_on_that_dimension():
    assert F.anchor_similarity((None, "flat"), ("neutral", "flat")) == 0.75


def test_null_downturn_counts_as_distance_one_on_that_dimension():
    assert F.anchor_similarity(("neutral", None), ("neutral", "flat")) == 0.75


# --- fit_anchor ----------------------------------------------------------

def test_shoe_in_its_own_good_set_scores_one():
    assert anchor(ASYM, families(ASYM), []) == 1.0


def test_shoe_in_its_own_bad_set_scores_zero():
    assert anchor(ASYM, [], families(ASYM)) == 0.0


def test_good_only_uses_max_not_mean():
    # sims to ASYM: itself 1.0, NEUTRAL 0.0 -> max 1.0, mean 0.5
    assert anchor(ASYM, families(ASYM, NEUTRAL), []) == 1.0


def test_good_and_bad_are_averaged():
    # good ASYM: sim 1.0. bad SEMI: distance (1+1)/4 -> sim 0.5, penalty term 0.5.
    assert anchor(ASYM, families(ASYM), families(SEMI)) == 0.75


def test_bad_only_is_one_minus_max_similarity():
    assert anchor(ASYM, [], families(SEMI)) == 0.5


def test_no_anchors_gives_none():
    assert anchor(ASYM, [], []) is None


# --- anchor_families -----------------------------------------------------

def test_anchor_families_looks_up_by_shoe_id():
    fams, _ = F.anchor_families([{"shoe_id": "n"}], {"n": NEUTRAL})
    assert fams == [("neutral", "flat")]


def test_missing_anchor_id_adds_warning():
    _, warnings = F.anchor_families([{"shoe_id": "gone"}], {"n": NEUTRAL})
    assert warnings == ["anchor_not_in_catalog:1"]


def test_missing_anchor_id_is_skipped_without_raising():
    fams, _ = F.anchor_families([{"shoe_id": "gone"}, {"shoe_id": "n"}], {"n": NEUTRAL})
    assert fams == [("neutral", "flat")]


# --- fit_score -----------------------------------------------------------

def test_fit_score_weights_anchor_by_lambda():
    expected = C.LAMBDA_ANCHOR * 1.0 + (1 - C.LAMBDA_ANCHOR) * 0.4
    assert F.fit_score(0.4, 1.0) == pytest.approx(expected)


def test_fit_score_with_only_cat_is_cat():
    assert F.fit_score(0.4, None) == 0.4


def test_fit_score_with_only_anchor_is_anchor():
    assert F.fit_score(None, 0.9) == 0.9


def test_fit_score_with_neither_is_none():
    assert F.fit_score(None, None) is None


# --- warnings and strict input ------------------------------------------

def test_missing_anchor_warning_carries_the_count():
    _, warnings = F.anchor_families([{"shoe_id": "g1"}, {"shoe_id": "g2"}], {})
    assert warnings == ["anchor_not_in_catalog:2"]


def test_missing_anchor_warning_does_not_leak_the_id():
    _, warnings = F.anchor_families([{"shoe_id": "secret-id"}], {})
    assert "secret-id" not in warnings[0]


def test_all_anchors_found_gives_no_warning():
    _, warnings = F.anchor_families([{"shoe_id": "n"}], {"n": NEUTRAL})
    assert warnings == []


def test_null_last_shape_warns_in_fit_cat():
    _, warnings = F.fit_cat({"toe_shape": "roman"}, {**ASYM, "last_shape": None})
    assert warnings == ["catalog_field_missing:last_shape"]


def test_null_last_shape_warns_once_for_toe_and_width():
    survey = {"toe_shape": "roman", "foot_width": "wide"}
    _, warnings = F.fit_cat(survey, {**ASYM, "last_shape": None})
    assert warnings == ["catalog_field_missing:last_shape"]


def test_null_closure_warns_in_fit_cat():
    _, warnings = F.fit_cat({"instep": "high"}, {**ASYM, "closure": None})
    assert warnings == ["catalog_field_missing:closure"]


def test_null_closure_does_not_warn_when_instep_unanswered():
    _, warnings = F.fit_cat({"toe_shape": "roman"}, {**ASYM, "closure": None})
    assert warnings == []


def test_complete_shoe_gives_no_fit_cat_warning():
    _, warnings = F.fit_cat({"toe_shape": "roman", "instep": "low"}, ASYM)
    assert warnings == []


def test_null_downturn_warns_in_fit_anchor():
    _, warnings = F.fit_anchor({**ASYM, "downturn": None}, families(ASYM), [])
    assert warnings == ["catalog_field_missing:downturn"]


def test_fit_anchor_does_not_warn_without_anchors():
    _, warnings = F.fit_anchor({**ASYM, "downturn": None}, [], [])
    assert warnings == []


def test_null_downturn_on_anchor_shoe_warns_in_anchor_families():
    _, warnings = F.anchor_families([{"shoe_id": "x"}], {"x": {**NEUTRAL, "downturn": None}})
    assert warnings == ["catalog_field_missing:downturn"]


@pytest.mark.parametrize("answer", [["roman"], 3, {"a": 1}])
def test_non_string_survey_answer_raises_scoring_error(answer):
    with pytest.raises(C.ScoringError):
        F.fit_cat({"toe_shape": answer}, ASYM)


def test_non_string_instep_answer_raises_scoring_error():
    with pytest.raises(C.ScoringError):
        F.fit_cat({"instep": ["high"]}, ASYM)


def test_unknown_closure_raises_scoring_error():
    with pytest.raises(C.ScoringError):
        F.fit_cat({"instep": "high"}, {**ASYM, "closure": "boa"})


def test_fit_module_reexports_the_config_scoring_error():
    assert F.ScoringError is C.ScoringError


def test_anchor_families_counts_an_entry_without_shoe_id_as_missing():
    _, warnings = F.anchor_families([{"brand": "x"}, {"shoe_id": "n"}], {"n": NEUTRAL})
    assert warnings == ["anchor_not_in_catalog:1"]
