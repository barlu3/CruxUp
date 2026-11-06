"""[W7-2-E] POST /recommend -- load one survey, score the active catalogue
with recommend/score.py, persist the ranking, return it.

The body is validated by hand in deps.survey_token_body, which runs before
get_conn so a bad body never opens a database connection, with no pydantic
model: FastAPI's own 422 echoes the offending `input` (here, the survey
token) and uses the `{"detail": ...}` envelope instead of this API's
`{"errors": [...]}`. The 422 message is fixed and never contains the
submitted value. An unknown token is a 404 with a fixed message; the token
is only ever a bound parameter, never part of SQL text, a body or a log line
(main.py's handlers log exception class + path only).

Persistence. The survey row is read FOR UPDATE so two concurrent re-requests
for one token serialise instead of interleaving their upserts and deletes.
Each recommendation is upserted on (survey_id, shoe_id); the conflict clause
rewrites only the scored columns and never the feedback columns (accepted,
satisfaction, returned, feedback_at). A row that already carries feedback is
not updated at all (`WHERE recommendation.feedback_at IS NULL`): it is the
record of what the user was shown when they gave that feedback, so its rank,
scores and scorer_version stay frozen even though the response reflects the
new ranking. Rows for shoes the new ranking no longer contains (gated out
after a changed catalogue or survey) are deleted unless they carry feedback,
for the same reason.

The row lock waits at most 5 s (SET LOCAL, so the setting ends with the
transaction). A timeout raises LockNotAvailable, an OperationalError, which
main.py masks as the generic 503. One commit at the end: any exception
before it leaves the transaction uncommitted and get_conn() closes it, which
rolls it back, so a failed request never half-writes a ranking.

Ids are selected `::text` because the survey's stored anchors reference
shoes by string id (survey/anchors.py) and score.py matches them by
equality. NUMERIC columns arrive as Decimal; score.py converts them, so they
are passed through untouched. ScoringError / ValueError from the scorer mean
a corrupt row or a model gap; they propagate to main.py's masked 500.

`RecommendationOut` extends `QuadrantShoeOut` so the frontend's quadrant
plot and the ranked list share one shoe shape.

Plain `def`, not `async def` -- same reasoning as routes/survey.py.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Literal

import psycopg
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

# Flat sibling import of the recommend package's directory, as score.py's own
# imports expect (see deps.py's module docstring on flat imports).
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "recommend"))
import score  # noqa: E402

from app.api.deps import get_conn, survey_token_body
from app.api.routes.quadrant import QuadrantShoeOut

router = APIRouter()

SURVEY_COLUMNS = (
    "foot_width", "instep", "toe_shape", "street_size",
    "known_good_shoes", "known_bad_shoes", "discipline", "terrain", "level",
    "goal_x_target", "goal_y_target", "budget_cap_usd",
)
SHOE_COLUMNS = (
    "id", "brand", "model", "version", "gender", "last_shape", "downturn",
    "closure", "msrp_usd", "quadrant_x_prior", "quadrant_y_prior",
    "prior_source", "status",
)


class TargetOut(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    x: float
    y: float


class TermsOut(BaseModel):
    fit: bool
    style: bool
    budget: bool


class GatedOutOut(BaseModel):
    over_budget: int
    size_unavailable: int
    unplaced: int


class RecommendationOut(QuadrantShoeOut):
    # NaN/inf would serialise as invalid JSON (or fail late); reject them
    # before commit instead.
    model_config = ConfigDict(allow_inf_nan=False)

    msrp_usd: float | None
    price_unknown: bool
    fit_score: float | None
    style_score: float | None
    budget_score: float | None
    total_score: float
    confidence: float
    confidence_label: Literal["high", "medium", "low"]
    rank: int
    warnings: list[str]


class RecommendOut(BaseModel):
    scorer_version: str
    target: TargetOut | None
    terms: TermsOut
    gated_out: GatedOutOut
    warnings: list[str]
    results: list[RecommendationOut]


class RecommendErrors(BaseModel):
    """Declared only so OpenAPI documents the 404/422 shape; the handler
    returns plain JSONResponses."""

    errors: list[str]


def load_survey(cur: psycopg.Cursor, token: str) -> tuple[Any, dict[str, Any]] | None:
    """The survey's id and scorer inputs, row-locked for this transaction."""
    # Same bound as deps.CONNECT_TIMEOUT_SECONDS: a request stuck behind
    # another for the same survey should fail, not hang the worker.
    cur.execute("SET LOCAL lock_timeout = '5s'")
    cur.execute(
        f"SELECT id, {', '.join(SURVEY_COLUMNS)} FROM user_survey "
        "WHERE survey_token = %(token)s FOR UPDATE",
        {"token": token},
    )
    row = cur.fetchone()
    if row is None:
        return None
    return row[0], dict(zip(SURVEY_COLUMNS, row[1:]))


def load_shoes(cur: psycopg.Cursor) -> list[dict[str, Any]]:
    # Every status, unfiltered: anchors must resolve against discontinued
    # shoes too; score.py itself drops non-active ones from the candidates.
    cur.execute(
        "SELECT id::text, brand, model, version, gender, last_shape, downturn, "
        "closure, msrp_usd, quadrant_x_prior, quadrant_y_prior, prior_source, status "
        "FROM shoe"
    )
    return [dict(zip(SHOE_COLUMNS, row)) for row in cur.fetchall()]


def load_size_rows(cur: psycopg.Cursor, street_size: Any) -> list[dict[str, Any]]:
    """Only the rows for the user's own street size; score.py ignores the rest."""
    cur.execute(
        "SELECT shoe_id::text, us_street_equiv, size_exists FROM shoe_size_map "
        "WHERE us_street_equiv = %(size)s",
        {"size": street_size},
    )
    return [
        {"shoe_id": r[0], "us_street_equiv": r[1], "size_exists": r[2]}
        for r in cur.fetchall()
    ]


def save_ranking(cur: psycopg.Cursor, survey_id: Any, ranking: score.Ranking) -> None:
    if ranking.results:
        cur.executemany(
            "INSERT INTO recommendation (survey_id, shoe_id, fit_score, style_score, "
            "budget_score, total_score, confidence, rank, scorer_version) "
            "VALUES (%(survey_id)s, %(shoe_id)s::uuid, %(fit_score)s, %(style_score)s, "
            "%(budget_score)s, %(total_score)s, %(confidence)s, %(rank)s, %(scorer_version)s) "
            "ON CONFLICT (survey_id, shoe_id) DO UPDATE SET "
            "fit_score = EXCLUDED.fit_score, style_score = EXCLUDED.style_score, "
            "budget_score = EXCLUDED.budget_score, total_score = EXCLUDED.total_score, "
            "confidence = EXCLUDED.confidence, rank = EXCLUDED.rank, "
            "scorer_version = EXCLUDED.scorer_version, created_at = now() "
            "WHERE recommendation.feedback_at IS NULL",
            [
                {
                    "survey_id": survey_id,
                    "shoe_id": r["id"],
                    "fit_score": r["fit_score"],
                    "style_score": r["style_score"],
                    "budget_score": r["budget_score"],
                    "total_score": r["total_score"],
                    "confidence": r["confidence"],
                    "rank": r["rank"],
                    "scorer_version": ranking.scorer_version,
                }
                for r in ranking.results
            ],
        )
    cur.execute(
        "DELETE FROM recommendation WHERE survey_id = %(sid)s AND feedback_at IS NULL "
        "AND NOT (shoe_id::text = ANY(%(kept)s::text[]))",
        {"sid": survey_id, "kept": [r["id"] for r in ranking.results]},
    )


def to_response(ranking: score.Ranking) -> dict[str, Any]:
    return {
        "scorer_version": ranking.scorer_version,
        "target": None if ranking.target is None
        else {"x": ranking.target[0], "y": ranking.target[1]},
        "terms": dict(ranking.terms),
        "gated_out": dict(ranking.gated_out),
        "warnings": list(ranking.warnings),
        "results": [dict(r) for r in ranking.results],
    }


@router.post(
    "/recommend",
    response_model=RecommendOut,
    responses={
        404: {
            "model": RecommendErrors,
            "description": "No survey exists for the given survey_token.",
        },
        422: {
            "model": RecommendErrors,
            "description": (
                'Body is not exactly {"survey_token": <token>}, or is not valid JSON.'
            ),
        },
    },
)
def create_recommendations(
    token: str = Depends(survey_token_body),
    conn: psycopg.Connection = Depends(get_conn),
):
    with conn.cursor() as cur:
        loaded = load_survey(cur, token)
        if loaded is None:
            return JSONResponse(status_code=404, content={"errors": ["survey not found"]})
        survey_id, survey = loaded
        shoes = load_shoes(cur)
        size_rows = (
            load_size_rows(cur, survey["street_size"])
            if survey["street_size"] is not None
            else []
        )
        ranking = score.recommend(survey, shoes, size_rows)
        save_ranking(cur, survey_id, ranking)
    # Validate BEFORE committing: a response-shape error must roll back
    # rather than persist a ranking the client never received.
    response = RecommendOut.model_validate(to_response(ranking))
    conn.commit()
    return response
