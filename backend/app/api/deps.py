"""[W7-1] FastAPI dependencies: database connection lifecycle and catalog
access for POST /survey and GET /shoes.

`database_url()` mirrors survey/store.py's own main()'s DATABASE_URL
resolution: the environment wins, and `config.load_dotenv()` is consulted
only if the variable is not already set. Resolved at USE time (inside
`get_conn`, on every request), never at import time -- config.py's own
module docstring names the exact failure mode an import-time read would
cause: an import that runs before .env is loaded would silently see
nothing. There is deliberately NO default connection string: if
DATABASE_URL is unset everywhere, the API fails closed via
`DatabaseNotConfigured`, rather than ever guessing at a database to connect
to.

`get_conn` is a generator dependency: one psycopg connection per request,
with a short, explicit `connect_timeout` so an unreachable database (e.g.
the unit CI job's `postgresql://localhost:1/unreachable`) fails fast with a
503 instead of hanging on the OS's own TCP timeout. The connection is ALWAYS
closed in `finally`, whether the request succeeded, was rejected by
validation, or raised -- closing (never committing) discards any
uncommitted transaction, so the read-only catalog lookups a 422 validation
failure leaves open are never committed.

`get_catalog` wraps that same connection in `anchors.PostgresCatalog` --
using the FLAT `anchors` module (see the sys.path manipulation below), the
exact same module object survey/store.py itself imports. Importing
`app.survey.anchors` instead would create a second, distinct module object,
silently diverging from the one store.py uses.

`json_body` parses the POST /survey request body itself rather than leaving
it to FastAPI's `Body()`. FastAPI turns only `json.JSONDecodeError` into a
RequestValidationError; anything else raised while parsing -- `RecursionError`
from deep nesting (~2 KB of brackets on Python <= 3.11; newer interpreters
tolerate far deeper), `UnicodeDecodeError` from invalid UTF-8 --
falls through its bare `except Exception` into a 400 `{"detail": ...}`,
outside this API's error envelope and outside its logging (review, card
W71-B/C). `json_body` catches `(ValueError, RecursionError)` -- exactly what
survey/store.py's CLI `main()` catches for the same reason -- and raises
`MalformedJSONBody`, which main.py maps to the survey 422 envelope. Parsing
is not validation: whatever parses, however wrong its shape, is handed to
`build_survey_row` untouched.

Tests override both `get_conn` and `get_catalog` via
`app.dependency_overrides` (see backend/tests/test_api.py, section B/C).
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psycopg
from fastapi import Depends, Request

# Flat sibling import of the survey package's own directory -- exactly the
# pattern store.py uses for itself (`sys.path.insert(0, str(Path(__file__)
# .resolve().parent))`), so `anchors` here and `anchors` inside store.py are
# the SAME module object (see the module docstring above).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "survey"))
import anchors  # noqa: E402

from app.config import load_dotenv

# A libpq-level connect timeout (seconds), not a Python-level one: without
# it, a connection attempt against an address nothing listens on can hang
# far longer than any reasonable request should wait.
CONNECT_TIMEOUT_SECONDS = 5


class DatabaseNotConfigured(Exception):
    """Raised by get_conn() when DATABASE_URL cannot be resolved from either
    the environment or .env. Mapped by main.py to the same generic 503 body
    as psycopg.OperationalError -- from a caller's perspective, "not
    configured" and "unreachable" are both simply "the database is not
    available right now"."""


class MalformedJSONBody(Exception):
    """Raised by json_body() when a JSON request body does not parse. The
    original parser error is chained as `__cause__`; its message (which can
    quote the body) is never sent to the client."""


def _is_json_content_type(value: str | None) -> bool:
    """Mirrors FastAPI's own rule: no content-type, application/json, or
    application/*+json. Anything else is not parsed as JSON. FastAPI parses
    the header with email.message.Message, which also strips RFC 822
    comments -- a form real clients do not send, so it is not replicated."""
    if not value:
        return True
    maintype, _, subtype = value.split(";", 1)[0].strip().lower().partition("/")
    return maintype == "application" and (subtype == "json" or subtype.endswith("+json"))


async def json_body(request: Request) -> Any:
    """The POST /survey body, parsed the way FastAPI's Body() parses it: an
    empty body is None, a JSON content type is parsed, and any other
    content type passes through as raw bytes (which build_survey_row then
    rejects as "payload must be a mapping"). The only difference is that
    every parse failure becomes MalformedJSONBody -- see the module
    docstring. `async` because reading the body needs the event loop; the
    parse itself is the same in-loop json.loads FastAPI performs."""
    raw = await request.body()
    if not raw:
        return None
    if not _is_json_content_type(request.headers.get("content-type")):
        return raw
    try:
        return json.loads(raw)
    except (ValueError, RecursionError) as exc:
        raise MalformedJSONBody("request body is not valid JSON") from exc


def database_url() -> str | None:
    """Resolve DATABASE_URL at USE time. The environment wins; `.env` is
    read only if the variable is not already set there -- mirrors
    survey/store.py's main() exactly, so the API and the CLI agree on where
    configuration comes from."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    load_dotenv()
    return os.environ.get("DATABASE_URL")


def get_conn() -> Iterator[psycopg.Connection]:
    """One psycopg connection per request. Fails closed with
    DatabaseNotConfigured if no DATABASE_URL is resolvable -- never falls
    back to a guessed default. Always closed in `finally`, so nothing a
    request leaves open (including an uncommitted, read-only transaction
    from a validation failure) is ever committed."""
    url = database_url()
    if not url:
        raise DatabaseNotConfigured("DATABASE_URL is not set (checked the environment and .env)")

    conn = psycopg.connect(url, connect_timeout=CONNECT_TIMEOUT_SECONDS)
    try:
        yield conn
    finally:
        conn.close()


def get_catalog(conn: psycopg.Connection = Depends(get_conn)) -> anchors.PostgresCatalog:
    """A PostgresCatalog over the request-scoped connection -- see the
    module docstring on why this must be the flat `anchors` module."""
    return anchors.PostgresCatalog(conn)
