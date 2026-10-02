"""[W7-1] Tests for backend/app/main.py -- the FastAPI app wrapping the
already-tested survey validation/persistence layer (survey/store.py) and
exposing the shoe catalog for the frontend's anchor picker.

Why these exist
----------------
`POST /survey` is contractually a THIN wrapper over
`store.build_survey_row()` / `store.insert_survey()`: it must add no
validation of its own, or the rules drift from the Python layer that
test_survey.py already pins. Section B's "multi-error payload" and "parity
property" tests exist specifically to catch that drift -- they assert the
API's error list is byte-for-byte what `build_survey_row()` itself returns,
not a paraphrase of it.

`GET /shoes` backs the frontend's anchor picker, and three real catalog
pairs share (brand, model) and differ only by `version` (and, for one pair,
`gender`) -- see anchors.py's own module docstring: Scarpa Instinct
(VS/VSR), La Sportiva Katana (Lace/Velcro), La Sportiva Solution (''
base/Comp). Section C's round-trip property is the acceptance criterion in
concrete form: whatever GET /shoes hands back must resolve, unambiguously,
back to itself through `anchors._resolve_one` -- so a picker can never
recreate the very ambiguity the catalog schema allows.

Style mirrors test_survey.py: a module docstring, lettered sections, no
shared state between tests (each test builds its own app/overrides rather
than reusing one at module scope), fakes shaped like test_survey.py's own
_FakeConn/_FakeCursor, and DB-backed tests that skip cleanly (never fail)
when no database is reachable.
"""

from __future__ import annotations

import copy
import inspect
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import psycopg
import pytest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
SURVEY_DIR = BACKEND_DIR / "app" / "survey"

# `app` is a package rooted at backend/ (run as `app.main` with backend/ on
# sys.path -- see main.py's own docstring); the survey modules are flat
# sibling imports through their own directory, exactly as store.py imports
# them and exactly as test_survey.py does here.
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(SURVEY_DIR))

import anchors as A  # noqa: E402
import schema as S  # noqa: E402
import store as ST  # noqa: E402

from app.main import create_app  # noqa: E402
from app.api.deps import DatabaseNotConfigured, get_catalog, get_conn  # noqa: E402
import app.api.deps as deps_module  # noqa: E402


# ==========================================================================
# Shared fakes
# ==========================================================================

def _catalog() -> A.StaticCatalog:
    """Mirrors test_survey.py's own `_catalog()` fixture -- the same seeded
    ambiguous pairs plus a couple of unambiguous shoes -- so a failure here
    means the API layer disagrees with store.py, not that the fixtures
    drifted from each other."""
    shoes = [
        A.CatalogShoe("id-solution-base", "La Sportiva", "Solution", "", "unisex"),
        A.CatalogShoe("id-solution-comp", "La Sportiva", "Solution", "Comp", "unisex"),
        A.CatalogShoe("id-katana-lace", "La Sportiva", "Katana", "Lace", "unisex"),
        A.CatalogShoe("id-katana-velcro", "La Sportiva", "Katana", "Velcro", "unisex"),
        A.CatalogShoe("id-instinct-vs", "Scarpa", "Instinct", "VS", "unisex"),
        A.CatalogShoe("id-instinct-vsr", "Scarpa", "Instinct", "VSR", "unisex"),
        A.CatalogShoe("id-drago", "Scarpa", "Drago", "", "unisex"),
        A.CatalogShoe("id-defy", "Evolv", "Defy", "", "mens"),
        A.CatalogShoe("id-elektra", "Evolv", "Defy", "", "womens"),
    ]
    aliases = {
        "Solution": "id-solution-base",
        "Solution Comp": "id-solution-comp",
        "Katana Lace": "id-katana-lace",
        "Katana Velcro": "id-katana-velcro",
        "Instinct VS": "id-instinct-vs",
        "Instinct VSR": "id-instinct-vsr",
        "VSR": "id-instinct-vsr",
        "Drago": "id-drago",
        "Defy": "id-defy",
    }
    return A.StaticCatalog(shoes, aliases)


class _FakeCursor:
    """Records execute() calls; can be told to raise on execute(), or to
    return canned rows from fetchall() -- one fake shape covers both
    POST /survey's INSERT path and GET /shoes' SELECT path. Mirrors
    test_survey.py's _FakeCursor, extended for the two features this file's
    tests need that store.py's own tests never exercised."""

    def __init__(self, calls, raise_on_execute=None, rows=None):
        self._calls = calls
        self._raise_on_execute = raise_on_execute
        self._rows = rows if rows is not None else []

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def execute(self, sql, params=None):
        self._calls.append((sql, params))
        if self._raise_on_execute is not None:
            raise self._raise_on_execute

    def fetchall(self):
        return self._rows


class _FakeConn:
    """Mirrors test_survey.py's _FakeConn, plus close() -- the API's
    get_conn() always closes in `finally`, so a fake standing in for a real
    connection must accept that call, and counts it so a test can prove it
    happened exactly once. `raise_on_commit` simulates a failure that is NOT
    a psycopg.Error (the catch-all 500 path)."""

    def __init__(self, raise_on_execute=None, rows=None, raise_on_commit=None):
        self.calls = []
        self.commits = 0
        self.rollbacks = 0
        self.close_calls = 0
        self._raise_on_execute = raise_on_execute
        self._raise_on_commit = raise_on_commit
        self._rows = rows

    @property
    def closed(self):
        return self.close_calls > 0

    def cursor(self):
        return _FakeCursor(self.calls, self._raise_on_execute, self._rows)

    def commit(self):
        if self._raise_on_commit is not None:
            raise self._raise_on_commit
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.close_calls += 1


def _client_with_overrides(conn=None, catalog=None):
    """A fresh app + TestClient per call -- never a shared module-level app
    -- so dependency_overrides from one test can never leak into another."""
    app = create_app()
    if conn is not None:
        app.dependency_overrides[get_conn] = lambda: conn
    if catalog is not None:
        app.dependency_overrides[get_catalog] = lambda: catalog
    return TestClient(app)


# ==========================================================================
# A. Wiring
# ==========================================================================

def _openapi_operations(app) -> dict[str, set[str]]:
    """Path -> HTTP methods, read from the OpenAPI schema rather than
    `app.routes`: FastAPI 0.14x wraps each included router in a private
    `_IncludedRouter`, so `app.routes` stops listing their paths at all.
    CI installs the unpinned (newest) FastAPI, so this must hold on both."""
    return {path: set(ops) for path, ops in app.openapi()["paths"].items()}


def test_post_survey_and_get_shoes_routes_are_registered():
    ops = _openapi_operations(create_app())
    assert ops.get("/survey") == {"post"}
    assert ops.get("/shoes") == {"get"}


def test_no_recommend_route_is_registered():
    """POST /recommend is W7-2, explicitly out of scope for this card.
    Checked in the schema AND by behaviour, so a route hidden from the
    schema (include_in_schema=False) could not slip through either."""
    app = create_app()
    assert "/recommend" not in _openapi_operations(app)
    assert TestClient(app).post("/recommend", json={}).status_code == 404


def test_post_survey_declares_nothing_for_fastapi_to_validate():
    """The "no validation of its own" rule, pinned at the framework level
    (round-2 review, W71-B): any Body(Model), Query() or Header() on this
    route would let FastAPI reject requests before build_survey_row() sees
    them -- a second rule set, with its own `{"detail": [...]}` 422 shape.
    FastAPI documents every such parameter in OpenAPI; the body parsed by
    deps.json_body, a Depends(), is deliberately not among them."""
    operation = create_app().openapi()["paths"]["/survey"]["post"]
    assert "requestBody" not in operation
    assert "parameters" not in operation


def test_no_cors_middleware_is_installed():
    """Recorded decision (2026-09-21): browser -> Next.js route handler ->
    FastAPI; the backend origin is never exposed to a browser directly."""
    app = create_app()
    assert not any(m.cls is CORSMiddleware for m in app.user_middleware)


def test_survey_and_shoes_handlers_are_plain_functions_not_coroutines():
    """psycopg is synchronous; FastAPI runs sync `def` handlers in its own
    threadpool so the event loop is never blocked -- `async def` here would
    silently block it instead. Read from each module's own APIRouter, which
    FastAPI does not wrap (unlike `app.routes` -- see _openapi_operations)."""
    from app.api.routes.shoes import router as shoes_router
    from app.api.routes.survey import router as survey_router

    endpoints = {
        route.path: route.endpoint
        for router in (survey_router, shoes_router)
        for route in router.routes
    }
    assert set(endpoints) == {"/survey", "/shoes"}
    for path, endpoint in endpoints.items():
        assert not inspect.iscoroutinefunction(endpoint), (
            f"{path} handler must be a plain `def`, not `async def`"
        )


# ==========================================================================
# B. POST /survey, hermetic
# ==========================================================================

def test_valid_full_submission_is_201_with_only_survey_token_and_one_insert():
    conn = _FakeConn()
    client = _client_with_overrides(conn=conn, catalog=_catalog())
    payload = {
        "foot_width": "narrow",
        "instep": "medium",
        "street_size": 9.5,
        "known_good_shoes": [{"brand": "Scarpa", "model": "Drago"}],
    }

    resp = client.post("/survey", json=payload)

    assert resp.status_code == 201
    body = resp.json()
    assert set(body) == {"survey_token"}

    assert len(conn.calls) == 1, "exactly one INSERT must run"
    sql, params = conn.calls[0]
    assert "INSERT INTO user_survey" in sql
    assert params["survey_token"] == body["survey_token"]
    assert conn.commits == 1
    assert conn.rollbacks == 0


@pytest.mark.parametrize(
    "payload",
    [{}, {"known_good_shoes": [{"brand": "Scarpa", "model": "Drago"}]}],
    ids=["completely-empty", "anchors-only"],
)
def test_empty_and_anchors_only_payloads_are_accepted(payload):
    """The Python layer accepts both (test_survey.py section G); the API
    must not add a required field on top of it."""
    conn = _FakeConn()
    client = _client_with_overrides(conn=conn, catalog=_catalog())
    resp = client.post("/survey", json=payload)
    assert resp.status_code == 201
    assert set(resp.json()) == {"survey_token"}


def test_multi_error_payload_returns_every_error_in_one_response_and_writes_nothing():
    """Combines an unknown top-level key, a bad enum, an ambiguous anchor
    and an unknown shoe -- the API's error list must equal
    build_survey_row()'s own, in order, nothing added or dropped. This is
    the "no validation of its own" pin."""
    payload = {
        "email": "climber@example.com",
        "foot_width": "extra-wide",
        "known_good_shoes": [{"brand": "Scarpa", "model": "Instinct"}],
        "known_bad_shoes": [{"brand": "Nike", "model": "Air Max"}],
    }
    _, expected_errors = ST.build_survey_row(copy.deepcopy(payload), _catalog())
    assert len(expected_errors) == 4, "fixture payload must trip all four checks"

    conn = _FakeConn()
    client = _client_with_overrides(conn=conn, catalog=_catalog())
    resp = client.post("/survey", json=payload)

    assert resp.status_code == 422
    assert resp.json() == {"errors": expected_errors}
    assert conn.calls == []
    assert conn.commits == 0


PARITY_PAYLOADS = [
    ("numeric-scale-budget", {"budget_cap_usd": 199.999}),
    ("bool-as-number-street-size", {"street_size": True}),
    (
        "oversize-anchor-list",
        {"known_good_shoes": [{"brand": "Scarpa", "model": "Drago"}] * (S.MAX_ANCHORS_TOTAL + 1)},
    ),
    (
        "shoe_id-supplied-in-anchor",
        {"known_good_shoes": [{"brand": "Scarpa", "model": "Drago", "shoe_id": "attacker"}]},
    ),
    (
        "contradictory-good-and-bad",
        {
            "known_good_shoes": [{"brand": "Scarpa", "model": "Drago"}],
            "known_bad_shoes": [{"brand": "SCARPA", "model": "DRAGO"}],
        },
    ),
    (
        "over-long-size",
        {"known_good_shoes": [{"brand": "Scarpa", "model": "Drago", "size": "x" * (A.ANCHOR_SIZE_MAX_LEN + 1)}]},
    ),
    (
        "size-contains-an-email-address",
        {"known_good_shoes": [{"brand": "Scarpa", "model": "Drago", "size": "a.person@example.com"}]},
    ),
    ("invalid-unknown-top-level-key", {"nickname": "climber"}),
    ("invalid-ambiguous-instinct", {"known_good_shoes": [{"brand": "Scarpa", "model": "Instinct"}]}),
    ("valid-empty", {}),
    (
        "valid-disambiguated-anchor",
        {"known_good_shoes": [{"brand": "Scarpa", "model": "Instinct", "version": "VSR"}]},
    ),
    (
        "valid-full-scalars",
        {
            "foot_width": "wide",
            "instep": "low",
            "toe_shape": "roman",
            "arch": "medium",
            "heel_fit": "narrow",
            "street_size": 10.0,
            "discipline": "trad",
            "terrain": "crack",
            "level": "intermediate",
            "goal_x_target": -0.5,
            "goal_y_target": 0.25,
            "budget_cap_usd": 150.0,
        },
    ),
]


@pytest.mark.parametrize("case_id,payload", PARITY_PAYLOADS, ids=[c[0] for c in PARITY_PAYLOADS])
def test_api_201_iff_build_survey_row_has_no_errors_and_422_lists_are_identical(case_id, payload):
    """The parity property: the API must return 201 exactly when
    build_survey_row() reports no errors, and on 422 the error lists must be
    identical -- never a superset, subset, or paraphrase."""
    _, expected_errors = ST.build_survey_row(copy.deepcopy(payload), _catalog())

    conn = _FakeConn()
    client = _client_with_overrides(conn=conn, catalog=_catalog())
    resp = client.post("/survey", json=payload)

    if expected_errors:
        assert resp.status_code == 422, f"{case_id}: expected 422, got {resp.status_code}: {resp.text}"
        assert resp.json() == {"errors": expected_errors}, case_id
        assert conn.calls == [], f"{case_id}: an invalid submission must never reach INSERT"
    else:
        assert resp.status_code == 201, f"{case_id}: expected 201, got {resp.status_code}: {resp.text}"
        assert set(resp.json()) == {"survey_token"}, case_id


@pytest.mark.parametrize(
    "kwargs",
    [
        {"json": ["not", "a", "mapping"]},
        {"json": "just a string"},
        {"json": 42},
        {"json": None},
        {"content": b""},
        {"content": b"plain text body", "headers": {"content-type": "text/plain"}},
    ],
    ids=["list", "string", "number", "null", "empty-body", "text-plain"],
)
def test_non_mapping_bodies_get_422_with_the_python_layers_message_not_fastapis(kwargs):
    """A JSON list/str/number/null, an empty body, and a text/plain body all
    reach `payload: Any = Depends(json_body)` untouched and flow into
    build_survey_row(), which reports "payload must be a mapping" -- never
    FastAPI's own `{"detail": [...]}` shape."""
    conn = _FakeConn()
    client = _client_with_overrides(conn=conn, catalog=_catalog())
    resp = client.post("/survey", **kwargs)

    assert resp.status_code == 422
    body = resp.json()
    assert list(body) == ["errors"]
    assert len(body["errors"]) == 1
    assert "payload must be a mapping" in body["errors"][0]
    assert conn.calls == []


def test_malformed_json_returns_the_generic_envelope_and_never_touches_the_db():
    conn = _FakeConn()
    client = _client_with_overrides(conn=conn, catalog=_catalog())
    resp = client.post(
        "/survey", content=b"{not valid json", headers={"content-type": "application/json"}
    )
    assert resp.status_code == 422
    assert resp.json() == {"errors": ["request body is not valid JSON"]}
    assert conn.calls == []


# Deep enough that json.loads raises RecursionError (not JSONDecodeError) on
# EVERY supported interpreter. Not tied to sys.getrecursionlimit(): that
# governs the C scanner only up to 3.11 (~2 KB of brackets overflows 3.9).
# 3.12/3.13 count against a separate C limit (<= 10k), and 3.14 guards by
# actual stack use -- measured parsing 100,000 levels cleanly and overflowing
# only at 200,000. A million levels (~2 MB) clears all of them, even on a
# 16 MB thread stack.
_TOO_DEEP = 1_000_000


@pytest.mark.parametrize(
    "body",
    [
        b"{not valid json",
        b"[" * _TOO_DEEP + b"]" * _TOO_DEEP,
        b'{"a":' * _TOO_DEEP + b"1" + b"}" * _TOO_DEEP,
        b'{"foot_width": "\xff\xfe"}',
    ],
    ids=["malformed", "deep-array", "deep-object", "invalid-utf8"],
)
def test_every_body_parse_failure_uses_the_errors_envelope_never_fastapis_400(body):
    """Review finding W71-B/C (both reviewers, independently): FastAPI's own
    body parsing turns only JSONDecodeError into a RequestValidationError;
    RecursionError from deep nesting fell through its bare `except
    Exception` to a 400 `{"detail": ...}` -- a second error shape that also
    bypassed server-side logging. Every parse failure must use the one
    envelope, the way store.main() catches (ValueError, RecursionError)."""
    conn = _FakeConn()
    client = _client_with_overrides(conn=conn, catalog=_catalog())
    resp = client.post("/survey", content=body, headers={"content-type": "application/json"})

    assert resp.status_code == 422, resp.text
    assert resp.json() == {"errors": ["request body is not valid JSON"]}
    assert conn.calls == [], "a body that never parsed must never reach the database"


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"content-type": "application/json"},
        {"content-type": "application/json; charset=utf-8"},
        {"content-type": "application/merge-patch+json"},
    ],
    ids=["no-content-type", "json", "json-charset", "plus-json"],
)
def test_json_content_types_are_parsed_like_fastapi_parses_them(headers):
    """The body parser replaced FastAPI's; it must accept exactly what
    FastAPI accepted (no header, application/json, application/*+json) or
    the move would have quietly narrowed the contract."""
    conn = _FakeConn()
    client = _client_with_overrides(conn=conn, catalog=_catalog())
    # httpx sends no content-type for a raw `content=` body, so `{}` really
    # is the "no header" case.
    resp = client.post("/survey", content=b'{"foot_width": "narrow"}', headers=headers)

    assert resp.status_code == 201, resp.text
    assert set(resp.json()) == {"survey_token"}


def test_body_parse_failure_is_logged_without_the_body(caplog):
    """The 400 path bypassed `_log_and_mask` entirely (W71-C). A parse failure
    must now be visible in the server log -- and the log line must not carry
    the submitted content."""
    client = _client_with_overrides(conn=_FakeConn(), catalog=_catalog())
    with caplog.at_level("ERROR", logger="app.main"):
        resp = client.post(
            "/survey",
            content=b"[" * _TOO_DEEP + b'"LOG_MARKER"' + b"]" * _TOO_DEEP,
            headers={"content-type": "application/json"},
        )
    assert resp.status_code == 422
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "POST /survey" in logged
    assert "LOG_MARKER" not in logged


# --- Error hygiene -----------------------------------------------------

def test_operational_error_from_get_conn_is_503_without_leaking_the_marker():
    app = create_app()

    def _raise_operational():
        raise psycopg.OperationalError("SECRET_MARKER_OPERATIONAL")

    app.dependency_overrides[get_conn] = _raise_operational
    app.dependency_overrides[get_catalog] = lambda: _catalog()
    client = TestClient(app)

    resp = client.post("/survey", json={"foot_width": "narrow"})

    assert resp.status_code == 503
    assert resp.json() == {"detail": "database unavailable"}
    assert "SECRET_MARKER_OPERATIONAL" not in resp.text


@pytest.mark.parametrize(
    "exc",
    [
        psycopg.errors.UniqueViolation("SECRET_MARKER_UNIQUE_VIOLATION"),
        psycopg.Error("SECRET_MARKER_GENERIC_DB_ERROR"),
    ],
    ids=["unique-violation", "generic-psycopg-error"],
)
def test_db_error_during_insert_is_500_without_leaking_the_marker(exc):
    """Injected by making the fake cursor's execute() raise -- store.py is
    never monkeypatched."""
    conn = _FakeConn(raise_on_execute=exc)
    client = _client_with_overrides(conn=conn, catalog=_catalog())

    resp = client.post("/survey", json={"foot_width": "narrow"})

    assert resp.status_code == 500
    assert resp.json() == {"detail": "could not complete the request"}
    assert "SECRET_MARKER" not in resp.text


def test_fail_closed_when_database_url_is_unset_never_attempts_a_connection(monkeypatch):
    """Uses the REAL get_conn (no dependency_overrides): with DATABASE_URL
    unset everywhere (env and .env), get_conn must raise the "not
    configured" exception -- mapped to 503 -- and must never even try
    psycopg.connect()."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(deps_module, "load_dotenv", lambda *a, **kw: [])

    def _fail_if_called(*args, **kwargs):
        pytest.fail("psycopg.connect must not be called when DATABASE_URL is unset")

    monkeypatch.setattr(psycopg, "connect", _fail_if_called)

    app = create_app()
    client = TestClient(app)
    resp = client.post("/survey", json={"foot_width": "narrow"})

    assert resp.status_code == 503
    assert resp.json() == {"detail": "database unavailable"}


def test_unexpected_non_db_exception_is_a_json_500_logged_and_masked(caplog):
    """Review finding W71-C: an exception that is not a psycopg.Error fell
    through to Starlette's plain-text `Internal Server Error`, outside every
    registered handler and so never logged. It must get the same generic
    JSON body and a log line, with no exception text in either."""
    conn = _FakeConn(raise_on_commit=RuntimeError("SECRET_MARKER_RUNTIME"))
    app = create_app()
    app.dependency_overrides[get_conn] = lambda: conn
    app.dependency_overrides[get_catalog] = lambda: _catalog()
    # Starlette re-raises a catch-all-handled exception after responding so
    # servers can log it; the test client would re-raise it too by default.
    client = TestClient(app, raise_server_exceptions=False)

    with caplog.at_level("ERROR", logger="app.main"):
        resp = client.post("/survey", json={"foot_width": "narrow"})

    assert resp.status_code == 500
    assert resp.json() == {"detail": "could not complete the request"}
    assert "SECRET_MARKER" not in resp.text
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "RuntimeError" in logged and "POST /survey" in logged
    assert "SECRET_MARKER" not in logged


# --- The REAL get_conn(): one connection per request, always closed --------
#
# Every other hermetic test replaces get_conn with a plain callable, which
# never runs its `finally: conn.close()` (review finding W71-B). These keep the
# real dependency and stub only psycopg.connect underneath it.

@pytest.fixture()
def real_get_conn(monkeypatch):
    """Patch psycopg.connect to hand out _FakeConns, record each one, and
    return the list. DATABASE_URL is set to a dummy so database_url() never
    reads the developer's .env."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://stub.invalid/never-dialled")
    opened: list = []
    pending: dict = {}

    def _connect(url, **kwargs):
        conn = _FakeConn(**pending)
        opened.append(conn)
        return conn

    monkeypatch.setattr(psycopg, "connect", _connect)
    return opened, pending


@pytest.mark.parametrize(
    "fake_kwargs,payload,expected_status,expected_commits",
    [
        ({}, {"known_good_shoes": [{"brand": "Scarpa", "model": "Drago"}]}, 201, 1),
        ({}, {"foot_width": "extra-wide"}, 422, 0),
        ({"raise_on_execute": psycopg.Error("x")}, {"foot_width": "narrow"}, 500, 0),
        ({"raise_on_commit": RuntimeError("x")}, {"foot_width": "narrow"}, 500, 0),
    ],
    ids=["created", "invalid", "psycopg-error", "non-db-error"],
)
def test_real_get_conn_opens_one_connection_and_closes_it_on_every_path(
    real_get_conn, fake_kwargs, payload, expected_status, expected_commits
):
    """One connect() per request, shared by the catalog read and the INSERT,
    and closed exactly once whether the request succeeded, failed
    validation, or raised. Closing without committing is what discards a
    422's open read transaction."""
    opened, pending = real_get_conn
    pending.update(fake_kwargs)
    app = create_app()
    app.dependency_overrides[get_catalog] = lambda: _catalog()  # get_conn stays real
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.post("/survey", json=payload)

    assert resp.status_code == expected_status, resp.text
    assert len(opened) == 1, "exactly one connection per request"
    assert opened[0].close_calls == 1
    assert opened[0].commits == expected_commits


def test_real_get_conn_closes_the_connection_after_get_shoes(real_get_conn):
    opened, _ = real_get_conn
    client = TestClient(create_app())

    resp = client.get("/shoes")

    assert resp.status_code == 200
    assert len(opened) == 1 and opened[0].close_calls == 1
    assert opened[0].commits == 0, "a read-only endpoint must never commit"


def test_database_not_configured_is_a_distinct_exception_type():
    """Sanity check on the fixture above: DatabaseNotConfigured must be its
    own exception, not accidentally aliased to psycopg.OperationalError (or
    the 503 test above would pass for the wrong reason)."""
    assert issubclass(DatabaseNotConfigured, Exception)
    assert not issubclass(DatabaseNotConfigured, psycopg.Error)


# ==========================================================================
# C. GET /shoes, hermetic
# ==========================================================================

def _canned_shoe_rows():
    """UUID objects for `id` (proves the route casts to str), covering all
    three ambiguous pairs plus a couple of unambiguous shoes."""
    return [
        (uuid.uuid4(), "Scarpa", "Instinct", "VS", "unisex"),
        (uuid.uuid4(), "Scarpa", "Instinct", "VSR", "unisex"),
        (uuid.uuid4(), "La Sportiva", "Katana", "Lace", "unisex"),
        (uuid.uuid4(), "La Sportiva", "Katana", "Velcro", "unisex"),
        (uuid.uuid4(), "La Sportiva", "Solution", "", "unisex"),
        (uuid.uuid4(), "La Sportiva", "Solution", "Comp", "unisex"),
        (uuid.uuid4(), "Scarpa", "Drago", "", "unisex"),
        (uuid.uuid4(), "Evolv", "Defy", "", "mens"),
        (uuid.uuid4(), "Evolv", "Defy", "", "womens"),
    ]


def _shoes_client(rows):
    conn = _FakeConn(rows=rows)
    app = create_app()
    app.dependency_overrides[get_conn] = lambda: conn
    return TestClient(app), conn


def test_get_shoes_returns_every_row_with_exactly_the_five_keys():
    rows = _canned_shoe_rows()
    client, _ = _shoes_client(rows)

    resp = client.get("/shoes")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == len(rows)
    for item in body:
        assert set(item) == {"id", "brand", "model", "version", "gender"}


def test_get_shoes_version_is_empty_string_for_base_models_not_null():
    rows = _canned_shoe_rows()
    client, _ = _shoes_client(rows)
    body = client.get("/shoes").json()

    base_solution = next(
        i for i in body if i["brand"] == "La Sportiva" and i["model"] == "Solution" and i["gender"] == "unisex"
        and i["version"] == ""
    )
    assert base_solution["version"] == ""


def test_get_shoes_ids_are_strings_matching_the_source_uuids():
    rows = _canned_shoe_rows()
    client, _ = _shoes_client(rows)
    body = client.get("/shoes").json()

    for item in body:
        assert isinstance(item["id"], str)
    assert {item["id"] for item in body} == {str(r[0]) for r in rows}


def test_all_three_ambiguous_pairs_appear_as_distinct_entries_with_distinct_versions():
    rows = _canned_shoe_rows()
    client, _ = _shoes_client(rows)
    body = client.get("/shoes").json()

    def versions_for(brand, model):
        return {i["version"] for i in body if i["brand"] == brand and i["model"] == model}

    assert versions_for("Scarpa", "Instinct") == {"VS", "VSR"}
    assert versions_for("La Sportiva", "Katana") == {"Lace", "Velcro"}
    assert versions_for("La Sportiva", "Solution") == {"", "Comp"}


def test_get_shoes_round_trips_through_resolve_one_for_every_item():
    """The heart of acceptance (3): for EVERY item GET /shoes returns, the
    anchor {brand, model, version, gender} taken from that item must resolve
    with anchors._resolve_one to exactly that item's id, with no ambiguity
    error -- so a picker that submits what GET /shoes gave it can never
    recreate the ambiguity."""
    rows = _canned_shoe_rows()
    client, _ = _shoes_client(rows)
    body = client.get("/shoes").json()

    catalog = A.StaticCatalog([A.CatalogShoe(str(r[0]), r[1], r[2], r[3], r[4]) for r in rows])

    for item in body:
        resolved, err = A._resolve_one(
            {
                "brand": item["brand"],
                "model": item["model"],
                "version": item["version"],
                "gender": item["gender"],
            },
            "known_good_shoes",
            0,
            catalog,
        )
        assert err is None, f"{item} failed to round-trip: {err}"
        assert resolved["shoe_id"] == item["id"]


# ==========================================================================
# D. DB-backed tests -- skip cleanly (never fail) when no database is
#    reachable, mirroring test_survey.py's own db_conn fixture. Must
#    actually RUN, not skip, when the DB is up: CI's integration job fails
#    on any skip while a database is available.
# ==========================================================================

def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    from app.config import load_dotenv

    load_dotenv()
    return os.environ.get("DATABASE_URL", "postgresql://localhost/cruxup")


@pytest.fixture()
def db_conn():
    try:
        conn = psycopg.connect(_database_url())
    except psycopg.OperationalError:
        pytest.skip("no reachable database at DATABASE_URL; DB-backed tests are optional")
        return
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


@pytest.fixture()
def live_client(db_conn):
    """The REAL app, with NO dependency overrides, so the real
    get_conn()/database_url() path is exercised end to end. `db_conn` is the
    skip gate; the app opens its own, separate connection(s)."""
    app = create_app()
    with TestClient(app) as client:
        yield client


def test_db_get_shoes_length_matches_live_count_and_pairs_are_present(live_client, db_conn):
    resp = live_client.get("/shoes")
    assert resp.status_code == 200
    body = resp.json()

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM shoe")
        (count,) = cur.fetchone()
    assert len(body) == count, "GET /shoes must return every row -- no status filter, no pagination"

    def versions_for(brand, model):
        return {i["version"] for i in body if i["brand"] == brand and i["model"] == model}

    assert versions_for("Scarpa", "Instinct") == {"VS", "VSR"}
    assert versions_for("La Sportiva", "Katana") == {"Lace", "Velcro"}
    assert versions_for("La Sportiva", "Solution") == {"", "Comp"}


def test_db_get_shoes_round_trips_against_the_live_postgres_catalog(live_client, db_conn):
    resp = live_client.get("/shoes")
    body = resp.json()
    catalog = A.PostgresCatalog(db_conn)

    for item in body:
        resolved, err = A._resolve_one(
            {
                "brand": item["brand"],
                "model": item["model"],
                "version": item["version"],
                "gender": item["gender"],
            },
            "known_good_shoes",
            0,
            catalog,
        )
        assert err is None, f"{item} failed to round-trip against the live catalog: {err}"
        assert resolved["shoe_id"] == item["id"]


def test_db_post_survey_persists_a_valid_submission_with_a_disambiguated_anchor(live_client, db_conn):
    """This is acceptance (1): a valid submission PERSISTS. Deliberately
    deviates from test_survey.py's "every DB test rolls back, none commits"
    stance -- persistence can only be proven by a real commit, observed from
    a SEPARATE, independent connection. Cleanup is unconditional (`finally`
    DELETE + COMMIT on db_conn) precisely because CI's integration job fails
    the build if any user_survey row is left behind, regardless of whether
    an assertion above it failed first.
    """
    with db_conn.cursor() as cur:
        cur.execute("SELECT id FROM shoe WHERE brand='Scarpa' AND model='Instinct' AND version='VSR'")
        row = cur.fetchone()
    assert row is not None, "fixture assumption: Scarpa Instinct VSR must exist in the seeded catalog"
    (real_vsr_id,) = row

    payload = {
        "foot_width": "narrow",
        "street_size": 9.5,
        "known_good_shoes": [{"brand": "Scarpa", "model": "Instinct", "version": "VSR"}],
    }

    token = None
    try:
        resp = live_client.post("/survey", json=payload)
        # Capture the token BEFORE any assertion: the row is already
        # committed by the time the response arrives, so cleanup must hinge
        # only on "the server handed back a token" -- never on a later
        # assertion also passing (review finding W71-B/C).
        body = resp.json() if resp.status_code == 201 else {}
        token = body.get("survey_token")
        assert resp.status_code == 201, resp.text
        assert set(body) == {"survey_token"}

        verify_conn = psycopg.connect(_database_url())
        try:
            with verify_conn.cursor() as cur:
                cur.execute(
                    "SELECT foot_width, street_size, known_good_shoes FROM user_survey "
                    "WHERE survey_token = %s",
                    (token,),
                )
                stored = cur.fetchone()
            assert stored is not None, "the row must be visible from a SEPARATE connection"
            stored_foot_width, stored_street_size, stored_good = stored
            assert stored_foot_width == "narrow"
            assert float(stored_street_size) == 9.5
            assert stored_good[0]["shoe_id"] == str(real_vsr_id)
        finally:
            verify_conn.close()
    finally:
        if token is not None:
            with db_conn.cursor() as cur:
                cur.execute("DELETE FROM user_survey WHERE survey_token = %s", (token,))
            db_conn.commit()


def test_db_post_survey_invalid_payload_leaves_user_survey_row_count_unchanged(live_client, db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM user_survey")
        (before,) = cur.fetchone()

    payload = {
        "known_good_shoes": [{"brand": "Scarpa", "model": "Instinct"}],  # ambiguous
        "street_size": "not-a-number",  # scalar error
    }
    resp = live_client.post("/survey", json=payload)

    assert resp.status_code == 422
    errors = resp.json()["errors"]
    assert any("ambiguous" in e.lower() and "VS" in e and "VSR" in e for e in errors)
    assert any("street_size" in e for e in errors)

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM user_survey")
        (after,) = cur.fetchone()
    assert after == before
