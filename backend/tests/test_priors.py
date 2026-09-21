"""[W5-1] Tests for spec-derived quadrant priors.

The point of these: the checked-in WEIGHTS are a fitted model, and a fitted
model silently degrades when the feature set or the calibration catalogue
changes. These pin the LOOCV score so that degradation fails a test instead of
quietly producing worse priors for 70 shoes nobody hand-checked.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy  # noqa: F401 -- hard import: a missing numpy must FAIL, not skip the regression guard
import pytest
import yaml

CATALOG_DIR = Path(__file__).resolve().parents[1] / "app" / "catalog"
sys.path.insert(0, str(CATALOG_DIR))
import priors as P  # noqa: E402

SHOES = yaml.safe_load((CATALOG_DIR / "data" / "shoes.yaml").read_text())["shoes"]


# --------------------------------------------------------------------------
# Contract with the database
# --------------------------------------------------------------------------

@pytest.mark.parametrize("shoe", SHOES, ids=lambda s: f"{s['brand']}-{s['model']}")
def test_derived_priors_satisfy_sql_constraints(shoe):
    """Must satisfy shoe_prior_x_range / shoe_prior_y_range, and be placeable."""
    x, y = P.derive_prior(shoe)
    assert -1 <= x <= 1 and -1 <= y <= 1
    assert x != 0 and y != 0, "a prior on an axis has no quadrant; validate.py rejects it"


def test_unknown_specs_still_produce_a_placeable_point():
    """A shoe with no spec fields at all must not crash or land on an axis."""
    x, y = P.derive_prior({})
    assert -1 <= x <= 1 and -1 <= y <= 1
    assert x != 0 and y != 0


def test_weight_vectors_match_feature_count():
    for axis in ("x", "y"):
        assert len(P.WEIGHTS[axis]) == len(P.FEATURE_NAMES), (
            f"WEIGHTS[{axis}] and FEATURE_NAMES are out of sync -- weights are "
            f"positional, so this silently mislabels every coefficient"
        )


# --------------------------------------------------------------------------
# The interaction terms are the reason this model beats the naive lookup
# --------------------------------------------------------------------------

def test_flat_and_stiff_reads_as_performance_not_comfort():
    """A flat STIFF shoe is an edging shoe. Flat alone would read as comfort."""
    edging = {"downturn": "flat", "last_shape": "semi-asymmetric",
              "stiffness_spec": "stiff", "closure": "lace"}       # Katana Lace
    comfort = {"downturn": "flat", "last_shape": "neutral",
               "stiffness_spec": "soft", "closure": "velcro"}     # gym shoe

    x_edging, _ = P.derive_prior(edging)
    x_comfort, _ = P.derive_prior(comfort)
    assert x_edging > x_comfort, "the flat_and_stiff interaction is not firing"


def test_stiffness_drives_the_y_axis_monotonically():
    base = {"downturn": "moderate", "last_shape": "asymmetric", "closure": "velcro"}
    ys = [P.derive_prior({**base, "stiffness_spec": s})[1]
          for s in ("stiff", "moderate-stiff", "moderate",
                    "moderate-soft", "soft", "very soft")]
    assert ys == sorted(ys), f"y should rise monotonically stiff -> soft, got {ys}"


def test_aggressive_downturn_is_more_performance_than_flat():
    base = {"last_shape": "asymmetric", "stiffness_spec": "soft", "closure": "velcro"}
    x_aggressive, _ = P.derive_prior({**base, "downturn": "aggressive"})
    x_flat, _ = P.derive_prior({**base, "downturn": "flat"})
    assert x_aggressive > x_flat


# --------------------------------------------------------------------------
# Regression guard on the fit itself
# --------------------------------------------------------------------------

def test_loocv_score_has_not_regressed():
    """Refit from scratch and confirm the model still clears section 9.2.

    Tolerance is generous -- this catches a broken feature set or a corrupted
    catalogue, not third-decimal drift.
    """
    hand = [s for s in SHOES if s.get("quadrant_x_prior") is not None]
    result = P.refit(hand)

    assert result["mae_x"] <= 0.20, f"MAE x regressed to {result['mae_x']:.3f}"
    assert result["mae_y"] <= 0.20, f"MAE y regressed to {result['mae_y']:.3f}"
    assert result["agreement"] >= 0.80, f"agreement fell to {result['agreement']:.0%}"

    assert abs(result["mae_x"] - P.LOOCV_MAE_X) < 0.05, (
        "LOOCV drifted from the documented value; refit and update the constants"
    )


def test_checked_in_weights_reproduce_the_documented_score():
    """WEIGHTS must be what refit() produces, not a stale paste."""
    hand = [s for s in SHOES if s.get("quadrant_x_prior") is not None]
    result = P.refit(hand)

    for axis in ("x", "y"):
        for i, (fitted, stored) in enumerate(zip(result[axis], P.WEIGHTS[axis])):
            assert abs(fitted - stored) < 0.01, (
                f"WEIGHTS[{axis}][{i}] ({P.FEATURE_NAMES[i]}) is {stored}, "
                f"but refit gives {fitted}. Re-run --refit and paste."
            )


# --------------------------------------------------------------------------
# Anchors
# --------------------------------------------------------------------------

def test_spec_model_places_most_anchors_correctly():
    """The section-3 anchors are hand-placed ground truth.

    The spec model is NOT required to reproduce all five -- it is a cheaper
    approximation and hand placement wins where they disagree. But if it gets
    most of them wrong it is not fit to place the other 70 shoes.
    """
    anchors = [s for s in SHOES if s.get("anchor")]
    assert len(anchors) == 5

    agree = sum(
        P.quadrant(*P.derive_prior(s))
        == P.quadrant(s["quadrant_x_prior"], s["quadrant_y_prior"])
        for s in anchors
    )
    assert agree >= 4, f"spec model agrees with only {agree}/5 anchors"


def test_prior_source_values_are_distinct():
    assert len({P.PriorSource.CORPUS, P.PriorSource.HAND, P.PriorSource.SPEC}) == 3
    assert P.PriorSource.SPEC.value == "spec"
