"""[W7-1] FastAPI entrypoint. Mounts api/routes: POST /survey, GET /shoes.

Run as `cd backend && uvicorn app.main:app`, or `uvicorn --app-dir backend
app.main:app` from the repo root -- either way, `app` is a package rooted at
`backend/`, and the survey modules underneath it (survey/anchors.py,
survey/store.py, survey/schema.py) are imported as FLAT sibling modules by
api/deps.py and api/routes/survey.py, exactly as store.py imports them for
itself. See api/deps.py's module docstring for why.

No CORS middleware -- a recorded decision (2026-09-21): the browser talks to
a Next.js route handler, which talks to this API; the backend's own origin
is never exposed to a browser directly, so there is nothing for CORS to
relax here.

Exception handling. Every handler below returns a body with no exception
text, no DSN, no SQL, and no submitted payload -- only a fixed, generic
string -- and logs server-side (stdlib `logging`: exception class name plus
request path only, never the payload) so an operator can still diagnose the
failure from the logs.

  * MalformedJSONBody (api/deps.py): a POST /survey body that does not
    parse -- malformed syntax, invalid UTF-8, or nesting past the recursion
    limit. 422 with the same `{"errors": [...]}` envelope every other survey
    error uses. The body is parsed by deps.json_body, not FastAPI's Body(),
    because FastAPI sent the last two to a 400 `{"detail": ...}` that no
    handler here saw (see deps.py).
  * DatabaseNotConfigured (api/deps.py): DATABASE_URL was not resolvable
    from the environment or .env. Mapped to the same 503 body as an
    OperationalError -- from a caller's perspective both just mean "the
    database is not available right now".
  * psycopg.OperationalError: connection failed or timed out (e.g. the unit
    CI job's deliberately unreachable DATABASE_URL).
  * psycopg.Error (the base class -- covers everything else, including
    UniqueViolation on a token collision): registered separately from
    OperationalError because Starlette resolves handlers by walking the
    exception's MRO and using the first match, so the more specific
    OperationalError handler above still wins for OperationalError itself;
    everything else lands here as a generic failure.
  * Exception (catch-all): anything else, e.g. a bug in this layer. Same
    generic 500 body as psycopg.Error, as JSON rather than Starlette's
    plain-text default, and logged like every other failure. Starlette
    re-raises the exception after this handler responds, so the server's
    own error log still records it.

Not handled here, deliberately: a request-body size cap and hiding
/docs + /openapi.json. The backend is reachable only through the Next.js
route handler (see above), which is the internet-facing choke point, so both
belong there (W6-1): it must allow-list exactly /survey and /shoes.
"""

from __future__ import annotations

import logging

import psycopg
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.deps import DatabaseNotConfigured, MalformedJSONBody
from app.api.routes.shoes import router as shoes_router
from app.api.routes.survey import router as survey_router

logger = logging.getLogger(__name__)

DATABASE_UNAVAILABLE_BODY = {"detail": "database unavailable"}
GENERIC_ERROR_BODY = {"detail": "could not complete the request"}


def _log_and_mask(exc: BaseException, request: Request) -> None:
    """Server-side only: exception class names + request path. Never the
    payload, the DSN, SQL, or exception text -- those never leave this
    function. The chained cause's class is included when there is one, so
    e.g. a RecursionError is distinguishable from a JSONDecodeError."""
    cause = f" (cause: {type(exc.__cause__).__name__})" if exc.__cause__ is not None else ""
    logger.error(
        "%s%s handling %s %s", type(exc).__name__, cause, request.method, request.url.path
    )


def create_app() -> FastAPI:
    app = FastAPI(title="CruxUp API")

    app.include_router(survey_router)
    app.include_router(shoes_router)

    @app.exception_handler(MalformedJSONBody)
    async def _malformed_json_handler(request: Request, exc: MalformedJSONBody):
        _log_and_mask(exc, request)
        return JSONResponse(status_code=422, content={"errors": ["request body is not valid JSON"]})

    @app.exception_handler(DatabaseNotConfigured)
    async def _not_configured_handler(request: Request, exc: DatabaseNotConfigured):
        _log_and_mask(exc, request)
        return JSONResponse(status_code=503, content=DATABASE_UNAVAILABLE_BODY)

    @app.exception_handler(psycopg.OperationalError)
    async def _operational_error_handler(request: Request, exc: psycopg.OperationalError):
        _log_and_mask(exc, request)
        return JSONResponse(status_code=503, content=DATABASE_UNAVAILABLE_BODY)

    @app.exception_handler(psycopg.Error)
    async def _db_error_handler(request: Request, exc: psycopg.Error):
        _log_and_mask(exc, request)
        return JSONResponse(status_code=500, content=GENERIC_ERROR_BODY)

    @app.exception_handler(Exception)
    async def _unexpected_error_handler(request: Request, exc: Exception):
        _log_and_mask(exc, request)
        return JSONResponse(status_code=500, content=GENERIC_ERROR_BODY)

    return app


app = create_app()
