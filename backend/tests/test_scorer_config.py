"""[W7-2-A] Tests for scorer_config.py: the single home of every
output-affecting scorer constant (timeline.md sections 7.2, 7.6, 7.7).

The constants are judgement-set, not tuned (D8). A failing test here is never
fixed by adjusting a constant to match -- see the snapshot test.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "recommend"))
import scorer_config as C  # noqa: E402


def test_scorer_version_is_v0_slice():
    assert C.SCORER_VERSION == "v0-slice"


def test_weights_sum_to_one():
    assert C.ALPHA + C.BETA + C.GAMMA == pytest.approx(1.0, abs=1e-9)


def test_all_constants_are_pinned():
    # This snapshot cannot force a SCORER_VERSION bump. It puts every
    # output-affecting change in the diff, next to SCORER_VERSION, so a reviewer
    # sees a value moved and can check the version moved with it.
    snapshot = {
        "SCORER_VERSION": C.SCORER_VERSION,
        "ALPHA": C.ALPHA,
        "BETA": C.BETA,
        "GAMMA": C.GAMMA,
        "LAMBDA_ANCHOR": C.LAMBDA_ANCHOR,
        "BUDGET_UNKNOWN_PRICE": C.BUDGET_UNKNOWN_PRICE,
        "C_PLACE_HAND": C.C_PLACE_HAND,
        "LABEL_HIGH": C.LABEL_HIGH,
        "LABEL_MEDIUM": C.LABEL_MEDIUM,
        "UNKNOWN_SUB_SCORE": C.UNKNOWN_SUB_SCORE,
        "NULL_STEP_DISTANCE": C.NULL_STEP_DISTANCE,
        "LAST_ORDINAL": dict(C.LAST_ORDINAL),
        "DOWNTURN_ORDINAL": dict(C.DOWNTURN_ORDINAL),
        "CLOSURE_ORDINAL": dict(C.CLOSURE_ORDINAL),
        "FIT_TOE_BY_LAST": {k: tuple(v) for k, v in C.FIT_TOE_BY_LAST.items()},
        "FIT_WIDTH_BY_LAST": {k: tuple(v) for k, v in C.FIT_WIDTH_BY_LAST.items()},
        "FIT_INSTEP_BY_CLOSURE": {k: dict(v) for k, v in C.FIT_INSTEP_BY_CLOSURE.items()},
    }
    assert snapshot == {
        "SCORER_VERSION": "v0-slice",
        "ALPHA": 0.45,
        "BETA": 0.40,
        "GAMMA": 0.15,
        "LAMBDA_ANCHOR": 0.7,
        "BUDGET_UNKNOWN_PRICE": 0.5,
        "C_PLACE_HAND": 0.80,
        "LABEL_HIGH": 0.70,
        "LABEL_MEDIUM": 0.45,
        "UNKNOWN_SUB_SCORE": 0.5,
        "NULL_STEP_DISTANCE": 1,
        "LAST_ORDINAL": {"neutral": 0, "semi-asymmetric": 1, "asymmetric": 2},
        "DOWNTURN_ORDINAL": {"flat": 0, "moderate": 1, "aggressive": 2},
        "CLOSURE_ORDINAL": {"slipper": 0, "velcro": 1, "lace": 2},
        "FIT_TOE_BY_LAST": {
            "egyptian": (0.6, 0.9, 1.0),
            "greek": (0.8, 0.8, 0.5),
            "roman": (1.0, 0.7, 0.4),
        },
        "FIT_WIDTH_BY_LAST": {
            "narrow": (0.6, 0.9, 1.0),
            "medium": (0.8, 1.0, 0.8),
            "wide": (1.0, 0.7, 0.4),
        },
        "FIT_INSTEP_BY_CLOSURE": {
            "low": {"lace": 1.0, "velcro": 0.9, "slipper": 0.9},
            "medium": {"lace": 1.0, "velcro": 0.9, "slipper": 0.8},
            "high": {"lace": 1.0, "velcro": 0.7, "slipper": 0.5},
        },
    }


def valid(**overrides):
    return {**C.current_config(), **overrides}


def test_scoring_error_is_defined_here_for_a_single_module_identity():
    assert C.ScoringError.__module__ == "scorer_config"


def test_valid_config_passes_the_check():
    assert C.check_config(valid()) is None


def test_broken_weight_sum_raises_runtime_error():
    with pytest.raises(RuntimeError):
        C.check_config(valid(ALPHA=0.5))


def test_negative_weight_raises_runtime_error():
    # sums to 1 on purpose: only the sign check can catch this
    with pytest.raises(RuntimeError):
        C.check_config(valid(ALPHA=-0.1, BETA=0.95, GAMMA=0.15))


def test_lambda_outside_unit_interval_raises_runtime_error():
    with pytest.raises(RuntimeError):
        C.check_config(valid(LAMBDA_ANCHOR=1.1))


@pytest.mark.parametrize("name", [
    "C_PLACE_HAND", "LABEL_HIGH", "LABEL_MEDIUM", "BUDGET_UNKNOWN_PRICE",
    "UNKNOWN_SUB_SCORE",
])
def test_scalar_outside_unit_interval_raises_runtime_error(name):
    with pytest.raises(RuntimeError):
        C.check_config(valid(**{name: 1.5}))


def test_inverted_label_thresholds_raise_runtime_error():
    with pytest.raises(RuntimeError):
        C.check_config(valid(LABEL_MEDIUM=0.70, LABEL_HIGH=0.45))


def test_table_value_above_one_raises_runtime_error():
    with pytest.raises(RuntimeError):
        C.check_config(valid(FIT_TOE_BY_LAST={**C.FIT_TOE_BY_LAST, "roman": (1.2, 0.7, 0.4)}))


def test_table_tuple_with_wrong_length_raises_runtime_error():
    with pytest.raises(RuntimeError):
        C.check_config(valid(FIT_WIDTH_BY_LAST={**C.FIT_WIDTH_BY_LAST, "wide": (1.0, 0.7)}))


def test_toe_table_with_missing_key_raises_runtime_error():
    with pytest.raises(RuntimeError):
        C.check_config(valid(FIT_TOE_BY_LAST={"egyptian": (0.6, 0.9, 1.0)}))


def test_width_table_with_extra_key_raises_runtime_error():
    with pytest.raises(RuntimeError):
        C.check_config(valid(FIT_WIDTH_BY_LAST={**C.FIT_WIDTH_BY_LAST, "huge": (1.0, 1.0, 1.0)}))


def test_instep_table_with_missing_closure_raises_runtime_error():
    with pytest.raises(RuntimeError):
        C.check_config(valid(FIT_INSTEP_BY_CLOSURE={
            **C.FIT_INSTEP_BY_CLOSURE, "low": {"lace": 1.0, "velcro": 0.9}}))
