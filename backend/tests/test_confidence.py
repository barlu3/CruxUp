"""[W7-2-C] Tests for confidence.py: recommendation confidence
(timeline.md section 7.7)."""

from __future__ import annotations

import itertools
import sys
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP_DIR / "recommend"))
sys.path.insert(0, str(APP_DIR / "catalog"))
import confidence as K  # noqa: E402
import scorer_config as config  # noqa: E402
import priors  # noqa: E402

ANCHOR = [{"shoe_id": "x"}]
FIT_FIELDS = {"foot_width": "wide", "toe_shape": "roman", "instep": "low"}


def test_hand_placement_confidence_is_point_eight():
    assert K.c_place("hand") == 0.80


def test_spec_placement_confidence_is_discounted_by_loocv_agreement():
    assert K.c_place("spec") == pytest.approx(0.80 * priors.LOOCV_AGREEMENT)


def test_spec_placement_confidence_matches_26_of_30():
    assert K.c_place("spec") == pytest.approx(0.80 * 26 / 30)


def test_corpus_placement_raises_scoring_error():
    with pytest.raises(config.ScoringError):
        K.c_place("corpus")


def test_unknown_prior_source_raises_scoring_error():
    with pytest.raises(config.ScoringError):
        K.c_place("vibes")


def test_anchors_only_survey_confidence_is_point_seven():
    assert K.c_survey({}, has_anchors=True) == pytest.approx(0.70)


def test_anchor_flag_alone_contributes_lambda():
    assert K.c_survey({}, has_anchors=True) == pytest.approx(0.70)


def test_three_fit_fields_without_anchors_is_point_three():
    assert K.c_survey(FIT_FIELDS, has_anchors=False) == pytest.approx(0.30)


def test_empty_survey_confidence_is_zero():
    assert K.c_survey({}, has_anchors=False) == 0.0


def test_full_survey_with_hand_placement_is_about_point_nine_oh_six():
    c = K.confidence(K.c_survey(FIT_FIELDS, has_anchors=True),
                     K.c_place("hand"), has_target=True)
    assert c == pytest.approx(0.906, abs=1e-3)


def test_missing_target_drops_the_placement_term():
    # (0.45 * 1.0 + 0) / 0.85
    assert K.confidence(1.0, 0.8, has_target=False) == pytest.approx(0.45 / 0.85)


def test_label_at_high_threshold_is_high():
    assert K.label(0.70) == "high"


def test_label_just_below_high_is_medium():
    assert K.label(0.6999) == "medium"


def test_label_at_medium_threshold_is_medium():
    assert K.label(0.45) == "medium"


def test_label_just_below_medium_is_low():
    assert K.label(0.4499) == "low"


@pytest.mark.parametrize(
    "c_survey, c_place, has_target",
    list(itertools.product([0.0, 1.0], [0.0, 1.0], [False, True])),
)
def test_confidence_stays_in_unit_interval(c_survey, c_place, has_target):
    assert 0.0 <= K.confidence(c_survey, c_place, has_target) <= 1.0


def test_raw_anchor_lists_are_ignored_when_none_resolved():
    # every anchor was dropped as not-in-catalog, so none count
    survey = {"known_good_shoes": ANCHOR, "known_bad_shoes": ANCHOR}
    assert K.c_survey(survey, has_anchors=False) == 0.0


def test_resolved_anchors_count_even_without_raw_lists():
    assert K.c_survey({}, has_anchors=True) == pytest.approx(0.70)


@pytest.mark.parametrize("bad", [1, 0, None, "yes"])
def test_non_bool_has_target_raises_type_error(bad):
    with pytest.raises(TypeError):
        K.confidence(1.0, 1.0, bad)


def test_no_target_confidence_can_never_be_high():
    assert K.label(K.confidence(1.0, 1.0, has_target=False)) == "medium"


def test_spec_placement_check_rejects_agreement_above_one():
    with pytest.raises(RuntimeError):
        K.check_spec_placement(0.8, 1.5)


def test_spec_placement_check_rejects_hand_confidence_above_one():
    with pytest.raises(RuntimeError):
        K.check_spec_placement(1.2, 0.9)


def test_spec_placement_check_accepts_current_values():
    assert K.check_spec_placement(config.C_PLACE_HAND, priors.LOOCV_AGREEMENT) is None
