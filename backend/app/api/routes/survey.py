"""[W7-1] POST /survey -- a THIN wrapper over the already-tested
survey/store.py: `store.build_survey_row()` (validate + resolve anchors) and
`store.insert_survey()` (persist). Adds NO validation of its own -- see
store.py / schema.py / anchors.py, which already own that entirely.
Otherwise the rules would drift from the Python layer those modules (and
test_survey.py) already pin.

The body is `payload: Any = Depends(json_body)` (api/deps.py) and deliberately carries
no pydantic model: a model would itself be a second layer of validation,
independent of schema.py, that could silently diverge from it. A dict, list,
str or null JSON body, an empty body (None), and a non-JSON content type (raw
bytes) all reach this handler UNTOUCHED and flow straight into
`build_survey_row`, which already rejects every non-mapping shape with its
own "payload must be a mapping, got <type>" error. Only a body that does not
parse at all is rejected before this handler runs -- `json_body` raises
MalformedJSONBody, which main.py maps to the same one-string error envelope.
(Why the body is not left to FastAPI's `Body()`: see deps.py.)

Plain `def`, not `async def`: psycopg (via store.py / anchors.py) is
synchronous, and FastAPI runs sync path operations in its own threadpool, so
a slow database round trip never blocks the event loop.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import psycopg
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Flat sibling imports -- the SAME `store` and `anchors` module objects
# app.api.deps.get_catalog() uses. See deps.py's module docstring on why
# `import app.survey.store` would be wrong here.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "survey"))
import anchors  # noqa: E402
import store  # noqa: E402

from app.api.deps import get_catalog, get_conn, json_body

router = APIRouter()


class SurveyCreated(BaseModel):
    """The ENTIRE 201 response body. Never the row, shoe_ids, or any
    submitted field -- survey_token is the sole handle (see store.py's
    module docstring: "the only identity is survey_token")."""

    survey_token: str


class SurveyErrors(BaseModel):
    """Declared only so OpenAPI documents the 422 shape; the handler itself
    returns a plain JSONResponse, never a validated instance of this model
    (see the module docstring on why: the error list must pass through
    verbatim, not be re-validated by a second schema)."""

    errors: list[str]


@router.post(
    "/survey",
    response_model=SurveyCreated,
    status_code=201,
    responses={422: {"model": SurveyErrors}},
)
def create_survey(
    payload: Any = Depends(json_body),
    conn: psycopg.Connection = Depends(get_conn),
    catalog: anchors.PostgresCatalog = Depends(get_catalog),
):
    row, errors = store.build_survey_row(payload, catalog)
    if errors:
        # Verbatim, in order, nothing added or dropped -- the "no validation
        # of its own" pin. insert_survey() is never called on this path.
        return JSONResponse(status_code=422, content={"errors": errors})

    token = store.insert_survey(conn, row)
    return SurveyCreated(survey_token=token)
