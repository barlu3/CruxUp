"""[W7-2-D] Persona tests: the scorer run over the real shoes.yaml catalogue.

Hermetic: shoes come from seed.load_catalog/_row with synthetic ids, no
database. Expectations are the section 3 anchor placements and the 2026-11-05
MSRP data; they are sanity checks on a judgement-set model (D8), not tuning
targets. A failing expectation is reported, never fixed by editing constants.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "app"
for sub in ("recommend", "catalog", "survey"):
    sys.path.insert(0, str(APP / sub))
import preferences  # noqa: E402
import score  # noqa: E402
import seed  # noqa: E402


@pytest.fixture(scope="module")
def shoes():
    rows = []
    for i, entry in enumerate(seed.load_catalog()):
        row = seed._row(entry)
        row["id"] = f"shoe-{i:02d}"
        row["status"] = "active"
        rows.append(row)
    return rows


def shoe_id(shoes, brand, model, version=""):
    return next(s["id"] for s in shoes
                if (s["brand"], s["model"], s["version"]) == (brand, model, version))


def survey_with_target(discipline, terrain, level, goal, **answers):
    """Store the target the way the survey store does."""
    x, y = preferences.target_quadrant(discipline, terrain, level, goal)
    return dict(discipline=discipline, terrain=terrain, level=level,
                goal_x_target=x, goal_y_target=y, **answers)


def rank_of(ranking, shoes, brand, model, version=""):
    sid = shoe_id(shoes, brand, model, version)
    return next(r["rank"] for r in ranking.results if r["id"] == sid)


def result_for(ranking, shoes, brand, model, version=""):
    sid = shoe_id(shoes, brand, model, version)
    return next((r for r in ranking.results if r["id"] == sid), None)


def above(ranking, shoes, better, worse):
    return rank_of(ranking, shoes, *better) < rank_of(ranking, shoes, *worse)


SOLUTION = ("La Sportiva", "Solution")
TC_PRO = ("La Sportiva", "TC Pro")
INSTINCT_VS = ("Scarpa", "Instinct", "VS")
DRAGO = ("Scarpa", "Drago")
MYTHOS = ("La Sportiva", "Mythos")
DEFY = ("Evolv", "Defy")
MOCCASYM = ("Five Ten", "Moccasym")


# --- P1: sport / overhang / advanced, performance goal ---------------------

@pytest.fixture(scope="module")
def p1(shoes):
    survey = survey_with_target("sport", "overhang", "advanced", 0.5,
                                toe_shape="egyptian", foot_width="narrow")
    return score.recommend(survey, shoes, [])


def test_p1_solution_ranks_above_tc_pro(p1, shoes):
    assert above(p1, shoes, SOLUTION, TC_PRO)


def test_p1_instinct_vs_ranks_above_tc_pro(p1, shoes):
    assert above(p1, shoes, INSTINCT_VS, TC_PRO)


# Section 3 puts sport performance in Q1 (performance + stiff: x > 0, y < 0),
# and the sport/overhang/advanced target lands there, so a nearest-quadrant
# ranking must lead with a Q1 shoe. (Q4, performance + soft, is overhang
# territory for boulder, not sport.)
def test_p1_top_result_is_in_q1(p1):
    assert p1.results[0]["quadrant"] == "Q1"


# --- P2: trad / crack, comfort goal, wide Roman foot -----------------------

@pytest.fixture(scope="module")
def p2(shoes):
    survey = survey_with_target("trad", "crack", None, -1,
                                toe_shape="roman", foot_width="wide")
    return score.recommend(survey, shoes, [])


def test_p2_tc_pro_ranks_above_drago(p2, shoes):
    assert above(p2, shoes, TC_PRO, DRAGO)


def test_p2_mythos_ranks_above_drago(p2, shoes):
    assert above(p2, shoes, MYTHOS, DRAGO)


def test_p2_mythos_has_unknown_price(p2, shoes):
    assert result_for(p2, shoes, *MYTHOS)["price_unknown"] is True


# --- P3: gym / slab / beginner, comfort goal, budget 120 -------------------

@pytest.fixture(scope="module")
def p3(shoes):
    survey = survey_with_target("gym", "slab", "beginner", -1,
                                toe_shape="greek", foot_width="medium",
                                budget_cap_usd=120)
    return score.recommend(survey, shoes, [])


def test_p3_origin_is_over_budget(p3, shoes):
    assert result_for(p3, shoes, "Scarpa", "Origin") is None


def test_p3_momentum_is_over_budget(p3, shoes):
    assert result_for(p3, shoes, "Black Diamond", "Momentum") is None


def test_p3_elektra_is_kept_with_unknown_price(p3, shoes):
    assert result_for(p3, shoes, "Evolv", "Elektra")["price_unknown"] is True


def test_p3_every_result_is_within_cap_or_price_unknown(p3):
    assert all(r["price_unknown"] or r["msrp_usd"] <= 120 for r in p3.results)


def test_p3_defy_ranks_above_moccasym(p3, shoes):
    assert above(p3, shoes, DEFY, MOCCASYM)


def test_p3_tarantulace_is_in_the_top_three(p3, shoes):
    assert rank_of(p3, shoes, "La Sportiva", "Tarantulace") <= 3


# --- P4: reported good fit --------------------------------------------------

# Run with the P1 target: with no target, every shoe sharing Solution's last
# and downturn ties it at fit 1.0 and the alphabetical tie-break decides, so
# "ranks first" is only meaningful once Style separates them.
@pytest.fixture(scope="module")
def p4(shoes):
    survey = survey_with_target("sport", "overhang", "advanced", 0.5)
    survey["known_good_shoes"] = [{"shoe_id": shoe_id(shoes, *SOLUTION)}]
    return score.recommend(survey, shoes, [])


def test_p4_reported_good_shoe_ranks_first(p4, shoes):
    assert rank_of(p4, shoes, *SOLUTION) == 1


def test_p4_reported_good_shoe_has_full_fit(p4, shoes):
    assert result_for(p4, shoes, *SOLUTION)["fit_score"] == 1.0


# Known limitation: with anchors and no target, only the coarse (last_shape,
# downturn) family separates shoes, so every shoe sharing Solution's family
# ties at fit 1.0 and the alphabetical tie-break decides the order.
def test_p4_anchor_only_without_target_ties_eight_shoes_at_full_fit(shoes):
    survey = {"known_good_shoes": [{"shoe_id": shoe_id(shoes, *SOLUTION)}]}
    ranking = score.recommend(survey, shoes, [])
    assert sum(1 for r in ranking.results if r["fit_score"] == 1.0) == 8


# --- P5: empty survey ---------------------------------------------------------

def test_p5_empty_survey_confidence_is_low_everywhere(shoes):
    ranking = score.recommend({}, shoes, [])
    assert {r["confidence_label"] for r in ranking.results} == {"low"}


# --- Emitted scores stay in [0, 1] (the frontend guard rejects anything else) ---

def test_every_emitted_score_and_confidence_is_within_unit_range(p1, p2, p3, p4, shoes):
    rankings = [p1, p2, p3, p4, score.recommend({}, shoes, [])]
    fields = ("fit_score", "style_score", "budget_score", "total_score", "confidence")
    values = [r[f] for ranking in rankings for r in ranking.results for f in fields]
    assert all(v is None or 0.0 <= v <= 1.0 for v in values)
