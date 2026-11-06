"""[W7-2-A] Every output-affecting constant of the v0 scorer, in one place
(timeline.md sections 7.2, 7.6, 7.7). Externalised on purpose: section 7.6
says the weights are set by judgment and documented, not tuned.

All values are JUDGEMENT-SET, NOT TUNED (D8). Tuning needs user-to-good-shoe
pairs, which do not exist yet; defer to post-launch section 9.3 data. Do not
adjust a value to make a test pass.

CHANGE ANY VALUE => BUMP SCORER_VERSION. Stored or compared scores are only
meaningful against the version that produced them; tests/test_scorer_config.py
pins every constant so a silent edit fails loudly.

Why each value
--------------
ALPHA 0.45 (Fit): heaviest, because a shoe that does not fit is useless no
    matter how well it matches the style.
BETA 0.40 (Style): the product's core idea is the comfort/performance x
    stiff/soft quadrant, so it is nearly as heavy as Fit.
GAMMA 0.15 (Budget): mostly a tie-breaker. The hard price gate in section 7.6
    already enforces the cap; this only prefers cheaper shoes among those that
    pass.
LAMBDA_ANCHOR 0.7: section 7.1 calls anchors the highest-signal fit input
    (lower noise than abstract self-report), so they get most of the weight
    when present, but not all of it: one anchor is a thin sample.
BUDGET_UNKNOWN_PRICE 0.5: a shoe with no known price is neither rewarded nor
    penalised by the budget term.
UNKNOWN_SUB_SCORE 0.5 / NULL_STEP_DISTANCE 1: a shoe field the catalog leaves
    NULL is treated as neutral (half score; one ordinal step of the two
    available) rather than as a match or a worst case. fit.py also emits a
    warning so the gap is visible.
C_PLACE_HAND 0.80: confidence in a hand-placed quadrant. The spec-derived
    confidence is derived from it in confidence.py (not typed here).
LABEL_HIGH 0.70 / LABEL_MEDIUM 0.45: cut points for the user-facing
    high/medium/low confidence label.

Fit_cat tables
--------------
A DOMAIN JUDGEMENT pending climber sign-off (W4'-3); the numbers encode
climbing folklore (e.g. a Roman toe box suffers in an asymmetric last that
crowds the big toe), not measurements. Last tables are tuples indexed by the
last ordinal (neutral, semi-asymmetric, asymmetric); the instep table is
keyed by closure.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any


# Every importer must use the flat module name (`import scorer_config`, never
# `app.recommend.scorer_config`): a second import path would create a second
# module object and a second ScoringError class that `except` would not match.
class ScoringError(Exception):
    """Input the scorer has no defined behaviour for (unknown enum value,
    unsupported prior source). Distinct from ValueError so callers can tell a
    scoring-model gap from a malformed request."""


SCORER_VERSION = "v0-slice"

ALPHA = 0.45
BETA = 0.40
GAMMA = 0.15

LAMBDA_ANCHOR = 0.7

BUDGET_UNKNOWN_PRICE = 0.5

UNKNOWN_SUB_SCORE = 0.5
NULL_STEP_DISTANCE = 1

C_PLACE_HAND = 0.80
LABEL_HIGH = 0.70
LABEL_MEDIUM = 0.45

# Mirror the shoe.downturn / shoe.closure CHECK enums and the survey vocabulary.
# The closure values are unused: the mapping exists so the instep table's keys
# are checked against the closure vocabulary.
LAST_ORDINAL = MappingProxyType({"neutral": 0, "semi-asymmetric": 1, "asymmetric": 2})
DOWNTURN_ORDINAL = MappingProxyType({"flat": 0, "moderate": 1, "aggressive": 2})
CLOSURE_ORDINAL = MappingProxyType({"slipper": 0, "velcro": 1, "lace": 2})

FIT_TOE_BY_LAST: Mapping[str, tuple[float, float, float]] = MappingProxyType({
    "egyptian": (0.6, 0.9, 1.0),
    "greek":    (0.8, 0.8, 0.5),
    "roman":    (1.0, 0.7, 0.4),
})

FIT_WIDTH_BY_LAST: Mapping[str, tuple[float, float, float]] = MappingProxyType({
    "narrow": (0.6, 0.9, 1.0),
    "medium": (0.8, 1.0, 0.8),
    "wide":   (1.0, 0.7, 0.4),
})

FIT_INSTEP_BY_CLOSURE: Mapping[str, Mapping[str, float]] = MappingProxyType({
    "low":    MappingProxyType({"lace": 1.0, "velcro": 0.9, "slipper": 0.9}),
    "medium": MappingProxyType({"lace": 1.0, "velcro": 0.9, "slipper": 0.8}),
    "high":   MappingProxyType({"lace": 1.0, "velcro": 0.7, "slipper": 0.5}),
})


def current_config() -> dict[str, Any]:
    return {
        "ALPHA": ALPHA,
        "BETA": BETA,
        "GAMMA": GAMMA,
        "LAMBDA_ANCHOR": LAMBDA_ANCHOR,
        "BUDGET_UNKNOWN_PRICE": BUDGET_UNKNOWN_PRICE,
        "UNKNOWN_SUB_SCORE": UNKNOWN_SUB_SCORE,
        "C_PLACE_HAND": C_PLACE_HAND,
        "LABEL_HIGH": LABEL_HIGH,
        "LABEL_MEDIUM": LABEL_MEDIUM,
        "FIT_TOE_BY_LAST": FIT_TOE_BY_LAST,
        "FIT_WIDTH_BY_LAST": FIT_WIDTH_BY_LAST,
        "FIT_INSTEP_BY_CLOSURE": FIT_INSTEP_BY_CLOSURE,
    }


_UNIT_SCALARS = (
    "LAMBDA_ANCHOR", "BUDGET_UNKNOWN_PRICE", "UNKNOWN_SUB_SCORE",
    "C_PLACE_HAND", "LABEL_HIGH", "LABEL_MEDIUM",
)
_TOE_KEYS = {"egyptian", "greek", "roman"}
_WIDTH_KEYS = {"narrow", "medium", "wide"}
_INSTEP_KEYS = {"low", "medium", "high"}


# Checked at IMPORT TIME, as in survey/preferences.py: a bad edit fails for
# every caller immediately. An explicit `raise`, not `assert`, because
# `python -O` strips asserts. Takes the values as a mapping so tests can
# present a broken copy without mutating the module.
def check_config(cfg: Mapping[str, Any]) -> None:
    for name in ("ALPHA", "BETA", "GAMMA"):
        if cfg[name] < 0:
            raise RuntimeError(f"{name}={cfg[name]} must be >= 0")
    total = cfg["ALPHA"] + cfg["BETA"] + cfg["GAMMA"]
    if abs(total - 1.0) > 1e-9:
        raise RuntimeError(f"ALPHA+BETA+GAMMA must be 1, got {total}")
    for name in _UNIT_SCALARS:
        if not 0.0 <= cfg[name] <= 1.0:
            raise RuntimeError(f"{name}={cfg[name]} outside [0, 1]")
    if not cfg["LABEL_MEDIUM"] < cfg["LABEL_HIGH"]:
        raise RuntimeError(
            f"LABEL_MEDIUM {cfg['LABEL_MEDIUM']} must be below LABEL_HIGH {cfg['LABEL_HIGH']}"
        )
    for name, keys in (("FIT_TOE_BY_LAST", _TOE_KEYS), ("FIT_WIDTH_BY_LAST", _WIDTH_KEYS)):
        _check_last_table(name, cfg[name], keys)
    _check_instep_table(cfg["FIT_INSTEP_BY_CLOSURE"])


def _check_last_table(name: str, table: Mapping, keys: set[str]) -> None:
    if set(table) != keys:
        raise RuntimeError(f"{name} keys {sorted(table)} must be {sorted(keys)}")
    for key, row in table.items():
        if len(row) != len(LAST_ORDINAL):
            raise RuntimeError(f"{name}[{key!r}] needs {len(LAST_ORDINAL)} entries, got {len(row)}")
        _check_unit_values(f"{name}[{key!r}]", row)


def _check_instep_table(table: Mapping) -> None:
    if set(table) != _INSTEP_KEYS:
        raise RuntimeError(f"FIT_INSTEP_BY_CLOSURE keys {sorted(table)} must be {sorted(_INSTEP_KEYS)}")
    for key, row in table.items():
        if set(row) != set(CLOSURE_ORDINAL):
            raise RuntimeError(
                f"FIT_INSTEP_BY_CLOSURE[{key!r}] closures {sorted(row)} "
                f"must be {sorted(CLOSURE_ORDINAL)}"
            )
        _check_unit_values(f"FIT_INSTEP_BY_CLOSURE[{key!r}]", row.values())


def _check_unit_values(where: str, values) -> None:
    for value in values:
        if not 0.0 <= value <= 1.0:
            raise RuntimeError(f"{where} value {value} outside [0, 1]")


check_config(current_config())
