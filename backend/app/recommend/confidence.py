"""[W7-2-C] Recommendation confidence (timeline.md section 7.7), survey-slice
edition: only the survey and the placement source feed it. The corpus terms
(N_j, agreement) arrive with W3-4, which also defines the corpus branch of
c_place.

C = (alpha * c_survey + beta * c_place * [has target]) / (alpha + beta),
reusing the Fit and Style weights so confidence tracks how much each term
contributed to the score. Without a target there is no Style term to be
confident about, so the placement term drops out rather than counting as 0.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[0] / "catalog"))
import priors  # noqa: E402
import scorer_config as config  # noqa: E402
from scorer_config import ScoringError  # noqa: E402

FIT_QUESTIONS = ("foot_width", "toe_shape", "instep")


def c_survey(survey: Mapping[str, Any], has_anchors: bool) -> float:
    """Anchors carry lambda of the weight (section 7.1: highest-signal input),
    the answered fit questions share the rest. has_anchors must come from the
    RESOLVED anchor families, not the raw survey lists: anchors dropped as
    not-in-catalog contributed no signal and must not raise confidence."""
    answered = sum(1 for q in FIT_QUESTIONS if survey.get(q) is not None)
    return (config.LAMBDA_ANCHOR * has_anchors
            + (1 - config.LAMBDA_ANCHOR) * answered / len(FIT_QUESTIONS))


def c_place(prior_source: str) -> float:
    # A spec placement is only as trustworthy as the model's held-out
    # agreement with hand placements, so it is derived from that rather than
    # typed: re-fitting priors.py moves it automatically.
    if prior_source == priors.PriorSource.HAND:
        return config.C_PLACE_HAND
    if prior_source == priors.PriorSource.SPEC:
        return config.C_PLACE_HAND * priors.LOOCV_AGREEMENT
    if prior_source == priors.PriorSource.CORPUS:
        raise ScoringError("corpus placement confidence is defined by W3-4")
    raise ScoringError(f"unknown prior_source {prior_source!r}")


def confidence(survey_conf: float, place_conf: float, has_target: bool) -> float:
    """Combine survey and placement confidence into [0, 1].

    Deliberate: with no target there is no Style term to be confident about,
    so only the survey term counts and C <= ALPHA/(ALPHA+BETA) = 0.45/0.85,
    about 0.53. A recommendation without a target can therefore never be
    labelled "high".
    """
    if not isinstance(has_target, bool):
        raise TypeError(f"has_target must be a bool, got {type(has_target).__name__}")
    placement = place_conf if has_target else 0.0
    return (config.ALPHA * survey_conf + config.BETA * placement) / (config.ALPHA + config.BETA)


def label(c: float) -> str:
    """Map a confidence to the user-facing "high" / "medium" / "low" label."""
    if c >= config.LABEL_HIGH:
        return "high"
    if c >= config.LABEL_MEDIUM:
        return "medium"
    return "low"


# Import-time, like scorer_config: the spec placement multiplies a config
# constant by a value that priors.py refits, so config's own checks cannot
# cover it.
def check_spec_placement(c_place_hand: float, loocv_agreement: float) -> None:
    for name, value in (("C_PLACE_HAND", c_place_hand), ("LOOCV_AGREEMENT", loocv_agreement),
                        ("spec placement", c_place_hand * loocv_agreement)):
        if not 0.0 <= value <= 1.0:
            raise RuntimeError(f"{name}={value} outside [0, 1]")


check_spec_placement(config.C_PLACE_HAND, priors.LOOCV_AGREEMENT)
