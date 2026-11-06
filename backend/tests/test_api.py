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
not a paraphrase of it. That includes q* derivation: the route sends a raw
`goal` answer to build_survey_row, which converts it to goal_x_target /
goal_y_target and refuses caller-supplied targets; the route itself does none
of that.

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
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
import pytest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
SURVEY_DIR = BACKEND_DIR / "app" / "survey"
CATALOG_DIR = BACKEND_DIR / "app" / "catalog"

# `app` is a package rooted at backend/ (run as `app.main` with backend/ on
# sys.path -- see main.py's own docstring); the survey modules are flat
# sibling imports through their own directory, exactly as store.py imports
# them and exactly as test_survey.py does here.
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(SURVEY_DIR))
# Index 2, after the two entries above: a future catalog module must not be
# able to shadow a survey module of the same name.
sys.path.insert(2, str(CATALOG_DIR))

import anchors as A  # noqa: E402
import preferences as P  # noqa: E402
import schema as S  # noqa: E402
import priors as PR  # noqa: E402
import store as ST  # noqa: E402
from validate import ANCHORS  # noqa: E402

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


def test_get_quadrant_route_is_registered_for_get_only():
    assert _openapi_operations(create_app()).get("/quadrant") == {"get"}


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


def test_survey_shoes_quadrant_and_recommend_handlers_are_plain_functions_not_coroutines():
    """psycopg is synchronous; FastAPI runs sync `def` handlers in its own
    threadpool so the event loop is never blocked -- `async def` here would
    silently block it instead. Read from each module's own APIRouter, which
    FastAPI does not wrap (unlike `app.routes` -- see _openapi_operations)."""
    from app.api.routes.quadrant import router as quadrant_router
    from app.api.routes.recommend import router as recommend_router
    from app.api.routes.shoes import router as shoes_router
    from app.api.routes.survey import router as survey_router

    endpoints = {
        route.path: route.endpoint
        for router in (survey_router, shoes_router, quadrant_router, recommend_router)
        for route in router.routes
    }
    assert set(endpoints) == {"/survey", "/shoes", "/quadrant", "/recommend"}
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


def _insert_params_for_goal_submission():
    conn = _FakeConn()
    client = _client_with_overrides(conn=conn, catalog=_catalog())
    client.post("/survey", json={"discipline": "trad", "goal": 1})
    return conn.calls[0][1]


def test_goal_submission_inserts_the_derived_target():
    assert _insert_params_for_goal_submission()["goal_x_target"] == -0.4


def test_goal_submission_inserts_no_goal_key():
    assert "goal" not in _insert_params_for_goal_submission()


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
            "goal": -0.5,
            "budget_cap_usd": 150.0,
        },
    ),
    ("invalid-goal-without-discipline", {"goal": 0.5}),
    ("invalid-goal-out-of-range", {"discipline": "gym", "goal": 2}),
    ("invalid-caller-supplied-goal-target", {"discipline": "gym", "goal_x_target": 0.1}),
    ("valid-discipline-plus-goal", {"discipline": "sport", "goal": 0.5}),
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


def test_real_get_conn_closes_the_connection_after_get_quadrant(real_get_conn):
    opened, _ = real_get_conn
    TestClient(create_app()).get("/quadrant")

    assert [c.close_calls for c in opened] == [1]


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
# C2. GET /quadrant, hermetic
# ==========================================================================

def _quadrant_row(brand="Scarpa", model="Drago", version="", gender="unisex",
                  x=Decimal("0.800"), y=Decimal("-0.400"), source="hand"):
    """Priors are Decimal because the column is NUMERIC(4,3) and psycopg
    returns NUMERIC as Decimal -- the route must convert them."""
    return (uuid.uuid4(), brand, model, version, gender, x, y, source)


def _quadrant_get(rows, raise_server_exceptions=True):
    conn = _FakeConn(rows=rows)
    app = create_app()
    app.dependency_overrides[get_conn] = lambda: conn
    client = TestClient(app, raise_server_exceptions=raise_server_exceptions)
    return client.get("/quadrant"), conn


def _quadrant_item(**row_kwargs):
    resp, _ = _quadrant_get([_quadrant_row(**row_kwargs)])
    return resp.json()[0]


def test_get_quadrant_items_have_exactly_the_ten_keys():
    assert set(_quadrant_item()) == {
        "id", "brand", "model", "version", "gender",
        "x", "y", "prior_source", "is_anchor", "quadrant",
    }


def test_get_quadrant_converts_decimal_priors_to_float():
    assert _quadrant_item(x=Decimal("0.800"))["x"] == 0.8


def test_get_quadrant_base_solution_is_an_anchor():
    assert _quadrant_item(brand="La Sportiva", model="Solution", version="")["is_anchor"] is True


def test_get_quadrant_solution_comp_is_not_an_anchor():
    assert _quadrant_item(brand="La Sportiva", model="Solution", version="Comp")["is_anchor"] is False


def test_get_quadrant_instinct_vs_is_not_an_anchor():
    assert _quadrant_item(brand="Scarpa", model="Instinct", version="VS")["is_anchor"] is False


def test_get_quadrant_instinct_vsr_is_an_anchor():
    assert _quadrant_item(brand="Scarpa", model="Instinct", version="VSR")["is_anchor"] is True


def test_get_quadrant_prior_source_literal_matches_the_prior_source_enum():
    from typing import get_args

    from app.api.routes.quadrant import QuadrantShoeOut

    annotation = QuadrantShoeOut.model_fields["prior_source"].annotation
    assert set(get_args(annotation)) == {s.value for s in PR.PriorSource}


def test_get_quadrant_negative_x_negative_y_is_q2():
    assert _quadrant_item(x=Decimal("-0.300"), y=Decimal("-0.600"))["quadrant"] == "Q2"


def test_get_quadrant_positive_x_positive_y_is_q4():
    assert _quadrant_item(x=Decimal("0.300"), y=Decimal("0.600"))["quadrant"] == "Q4"


def test_get_quadrant_empty_table_returns_an_empty_list():
    resp, _ = _quadrant_get([])
    assert resp.json() == []


def test_get_quadrant_positive_x_negative_y_is_q1():
    assert _quadrant_item(x=Decimal("0.700"), y=Decimal("-0.400"))["quadrant"] == "Q1"


def test_get_quadrant_negative_x_positive_y_is_q3():
    assert _quadrant_item(x=Decimal("-0.500"), y=Decimal("0.500"))["quadrant"] == "Q3"


def test_get_quadrant_spec_prior_source_passes_through():
    assert _quadrant_item(source="spec")["prior_source"] == "spec"


def test_get_quadrant_on_axis_x_row_is_a_500():
    resp, _ = _quadrant_get([_quadrant_row(x=Decimal("0.000"))], raise_server_exceptions=False)
    assert resp.status_code == 500


def test_get_quadrant_on_axis_x_row_has_the_generic_body():
    resp, _ = _quadrant_get([_quadrant_row(x=Decimal("0.000"))], raise_server_exceptions=False)
    assert resp.json() == {"detail": "could not complete the request"}


def test_get_quadrant_on_axis_y_row_is_a_500():
    resp, _ = _quadrant_get([_quadrant_row(y=Decimal("0.000"))], raise_server_exceptions=False)
    assert resp.status_code == 500


def test_get_quadrant_executes_its_sql_with_no_bind_parameters():
    _, conn = _quadrant_get([_quadrant_row()])
    assert [params for _, params in conn.calls] == [None]


def _quadrant_operational_error_response():
    app = create_app()

    def _raise_operational():
        raise psycopg.OperationalError("SECRET_MARKER_QUADRANT")

    app.dependency_overrides[get_conn] = _raise_operational
    return TestClient(app).get("/quadrant")


def test_get_quadrant_operational_error_is_503():
    assert _quadrant_operational_error_response().status_code == 503


def test_get_quadrant_operational_error_has_the_generic_body():
    assert _quadrant_operational_error_response().json() == {"detail": "database unavailable"}


def test_get_quadrant_operational_error_does_not_leak_the_marker():
    assert "SECRET_MARKER_QUADRANT" not in _quadrant_operational_error_response().text


# ==========================================================================
# C2. POST /recommend, hermetic
# ==========================================================================

RECOMMEND_TOKEN = "tok_AbC-123_secretvalue"

# Column order of the three SELECTs in routes/recommend.py, restated here so
# a reordering there fails these tests instead of silently mis-mapping rows.
_SURVEY_COLS = (
    "id", "foot_width", "instep", "toe_shape", "street_size",
    "known_good_shoes", "known_bad_shoes", "discipline", "terrain", "level",
    "goal_x_target", "goal_y_target", "budget_cap_usd",
)
_SHOE_COLS = (
    "id", "brand", "model", "version", "gender", "last_shape", "downturn",
    "closure", "msrp_usd", "quadrant_x_prior", "quadrant_y_prior",
    "prior_source", "status",
)


def _survey_tuple(**overrides):
    values = dict(
        id=uuid.UUID(int=1), foot_width="narrow", instep=None, toe_shape=None,
        street_size=None, known_good_shoes=[], known_bad_shoes=[],
        discipline=None, terrain=None, level=None,
        goal_x_target=Decimal("0.500"), goal_y_target=Decimal("0.500"),
        budget_cap_usd=Decimal("250.00"),
    )
    values.update(overrides)
    return tuple(values[c] for c in _SURVEY_COLS)


def _shoe_tuple(**overrides):
    values = dict(
        id="s-drago", brand="Scarpa", model="Drago", version="", gender="unisex",
        last_shape="asymmetric", downturn="aggressive", closure="velcro",
        msrp_usd=Decimal("199.00"), quadrant_x_prior=Decimal("0.800"),
        quadrant_y_prior=Decimal("0.600"), prior_source="hand", status="active",
    )
    values.update(overrides)
    return tuple(values[c] for c in _SHOE_COLS)


class _ScriptedCursor:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def execute(self, sql, params=None):
        self._conn.executes.append((sql, params))
        if self._conn.raise_on_execute is not None:
            raise self._conn.raise_on_execute

    def executemany(self, sql, rows):
        self._conn.executemanys.append((sql, list(rows)))

    def fetchone(self):
        return self._conn.fetchones.pop(0)

    def fetchall(self):
        return self._conn.fetchalls.pop(0)


class _ScriptedConn:
    """Answers fetchone()/fetchall() from queues, in call order, and records
    every execute()/executemany() with its SQL and parameters. Separate from
    _FakeConn, whose cursor can only return one canned fetchall()."""

    def __init__(self, fetchones=(), fetchalls=(), raise_on_execute=None):
        self.fetchones = list(fetchones)
        self.fetchalls = list(fetchalls)
        self.raise_on_execute = raise_on_execute
        self.executes = []
        self.executemanys = []
        self.commits = 0
        self.close_calls = 0

    def cursor(self):
        return _ScriptedCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        self.close_calls += 1


def _recommend_conn(survey=None, shoes=None, size_rows=None):
    """A conn for a known token. `size_rows` is only consumed when the survey
    sets street_size (the route skips the query otherwise)."""
    survey = _survey_tuple() if survey is None else survey
    shoes = [_shoe_tuple()] if shoes is None else shoes
    fetchalls = [shoes]
    if size_rows is not None:
        fetchalls.append(size_rows)
    return _ScriptedConn(fetchones=[survey], fetchalls=fetchalls)


def _post_recommend(conn, body=None, raise_server_exceptions=True):
    app = create_app()
    app.dependency_overrides[get_conn] = lambda: conn
    client = TestClient(app, raise_server_exceptions=raise_server_exceptions)
    return client.post("/recommend", json={"survey_token": RECOMMEND_TOKEN} if body is None else body)


def test_post_recommend_route_is_registered_for_post_only():
    assert _openapi_operations(create_app()).get("/recommend") == {"post"}


def test_post_recommend_declares_no_request_body_for_fastapi_to_validate():
    operation = create_app().openapi()["paths"]["/recommend"]["post"]
    assert "requestBody" not in operation


def test_recommend_malformed_json_is_422_with_the_errors_envelope():
    client = _client_with_overrides(conn=_ScriptedConn())
    resp = client.post("/recommend", content=b"{not json", headers={"content-type": "application/json"})
    assert (resp.status_code, resp.json()) == (422, {"errors": ["request body is not valid JSON"]})


RECOMMEND_BODY_ERROR = {"errors": ['body must be {"survey_token": <token>}']}


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"token": "abc"},
        {"survey_token": "abc", "extra": 1},
        {"survey_token": 123},
        {"survey_token": None},
        {"survey_token": ""},
        {"survey_token": "a" * 65},
        {"survey_token": "bad token!"},
        {"survey_token": "abc\n"},
        {"survey_token": "toké"},
        ["abc"],
        "abc",
    ],
    ids=["empty", "wrong-key", "extra-key", "int", "null", "empty-str", "65-chars",
         "bad-chars", "trailing-newline", "non-ascii", "list", "string"],
)
def test_recommend_invalid_body_is_422_with_the_fixed_message(body):
    conn = _ScriptedConn()
    resp = _client_with_overrides(conn=conn).post("/recommend", json=body)
    assert (resp.status_code, resp.json()) == (422, RECOMMEND_BODY_ERROR)


def test_recommend_missing_body_is_422():
    resp = _client_with_overrides(conn=_ScriptedConn()).post("/recommend")
    assert resp.status_code == 422


def test_recommend_64_char_token_passes_validation():
    conn = _ScriptedConn(fetchones=[None])
    resp = _client_with_overrides(conn=conn).post("/recommend", json={"survey_token": "a" * 64})
    assert resp.status_code == 404


def test_recommend_422_body_does_not_echo_the_submitted_token():
    bad = {"survey_token": RECOMMEND_TOKEN, "extra": 1}
    resp = _client_with_overrides(conn=_ScriptedConn()).post("/recommend", json=bad)
    assert RECOMMEND_TOKEN not in resp.text


def test_recommend_invalid_body_runs_no_sql():
    conn = _ScriptedConn()
    _client_with_overrides(conn=conn).post("/recommend", json={})
    assert conn.executes == []


def test_recommend_unknown_token_is_404():
    resp = _post_recommend(_ScriptedConn(fetchones=[None]))
    assert resp.status_code == 404


def test_recommend_unknown_token_body_is_exactly_the_fixed_envelope():
    resp = _post_recommend(_ScriptedConn(fetchones=[None]))
    assert resp.json() == {"errors": ["survey not found"]}


def test_recommend_unknown_token_never_commits():
    conn = _ScriptedConn(fetchones=[None])
    _post_recommend(conn)
    assert conn.commits == 0


def test_recommend_valid_token_is_200():
    assert _post_recommend(_recommend_conn()).status_code == 200


def test_recommend_reports_the_v0_slice_scorer_version():
    assert _post_recommend(_recommend_conn()).json()["scorer_version"] == "v0-slice"


def test_recommend_results_are_ordered_by_rank():
    shoes = [
        _shoe_tuple(id="s-a", model="Aaa", msrp_usd=Decimal("240.00")),
        _shoe_tuple(id="s-b", model="Bbb", msrp_usd=Decimal("100.00")),
        _shoe_tuple(id="s-c", model="Ccc", msrp_usd=Decimal("150.00")),
    ]
    results = _post_recommend(_recommend_conn(shoes=shoes)).json()["results"]
    assert [r["rank"] for r in results] == [1, 2, 3]


def test_recommend_cheaper_shoe_ranks_first_when_only_budget_differs():
    shoes = [
        _shoe_tuple(id="s-a", model="Aaa", msrp_usd=Decimal("240.00")),
        _shoe_tuple(id="s-b", model="Bbb", msrp_usd=Decimal("100.00")),
    ]
    results = _post_recommend(_recommend_conn(shoes=shoes)).json()["results"]
    assert results[0]["id"] == "s-b"


def test_recommend_null_msrp_shoe_has_price_unknown_true():
    shoes = [_shoe_tuple(msrp_usd=None)]
    result = _post_recommend(_recommend_conn(shoes=shoes)).json()["results"][0]
    assert (result["price_unknown"], result["msrp_usd"]) == (True, None)


def test_recommend_priced_shoe_has_price_unknown_false_and_a_float_msrp():
    result = _post_recommend(_recommend_conn()).json()["results"][0]
    assert (result["price_unknown"], result["msrp_usd"]) == (False, 199.0)


def test_recommend_survey_select_binds_the_token_as_a_parameter():
    conn = _recommend_conn()
    _post_recommend(conn)
    sql, params = conn.executes[1]
    assert (params, "%(token)s" in sql) == ({"token": RECOMMEND_TOKEN}, True)


def test_recommend_sql_text_never_contains_the_token():
    conn = _recommend_conn()
    _post_recommend(conn)
    assert not any(RECOMMEND_TOKEN in sql for sql, _ in conn.executes + conn.executemanys)


def test_recommend_survey_select_locks_the_row():
    conn = _recommend_conn()
    _post_recommend(conn)
    assert conn.executes[1][0].rstrip().endswith("FOR UPDATE")


def test_recommend_bounds_the_row_lock_wait_before_locking():
    conn = _recommend_conn()
    _post_recommend(conn)
    assert conn.executes[0] == ("SET LOCAL lock_timeout = '5s'", None)


def test_recommend_lock_timeout_is_the_masked_503():
    conn = _ScriptedConn(raise_on_execute=psycopg.errors.LockNotAvailable("lock timeout"))
    resp = _post_recommend(conn, raise_server_exceptions=False)
    assert (resp.status_code, resp.json()) == (503, {"detail": "database unavailable"})


def test_recommend_upsert_row_count_equals_result_count():
    shoes = [_shoe_tuple(id="s-a", model="Aaa"), _shoe_tuple(id="s-b", model="Bbb")]
    conn = _recommend_conn(shoes=shoes)
    body = _post_recommend(conn).json()
    assert len(conn.executemanys[0][1]) == len(body["results"])


def test_recommend_upsert_rows_carry_the_response_total_and_version():
    conn = _recommend_conn()
    body = _post_recommend(conn).json()
    row = conn.executemanys[0][1][0]
    assert (row["total_score"], row["scorer_version"], row["rank"]) == (
        body["results"][0]["total_score"], "v0-slice", 1)


def test_recommend_upsert_sql_never_touches_feedback_columns():
    conn = _recommend_conn()
    _post_recommend(conn)
    insert_part, conflict_part = conn.executemanys[0][0].split("ON CONFLICT")
    written = insert_part + conflict_part.split("WHERE")[0]
    assert not any(col in written for col in ("accepted", "satisfaction", "returned", "feedback_at"))


def test_recommend_delete_spares_rows_with_feedback_and_binds_kept_ids():
    conn = _recommend_conn()
    _post_recommend(conn)
    sql, params = conn.executes[-1]
    assert ("feedback_at IS NULL" in sql, params["kept"]) == (True, ["s-drago"])


def test_recommend_success_commits_exactly_once():
    conn = _recommend_conn()
    _post_recommend(conn)
    assert conn.commits == 1


def test_recommend_size_query_is_skipped_without_a_street_size():
    conn = _recommend_conn()
    _post_recommend(conn)
    assert not any("shoe_size_map" in sql for sql, _ in conn.executes)


def test_recommend_size_unavailable_shoe_is_gated_out_when_street_size_is_set():
    size_rows = [("s-drago", Decimal("9.5"), False)]
    conn = _recommend_conn(survey=_survey_tuple(street_size=Decimal("9.5")), size_rows=size_rows)
    body = _post_recommend(conn).json()
    assert (body["gated_out"]["size_unavailable"], body["results"]) == (1, [])


def test_recommend_size_query_binds_the_street_size():
    conn = _recommend_conn(survey=_survey_tuple(street_size=Decimal("9.5")), size_rows=[])
    _post_recommend(conn)
    sql, params = next(c for c in conn.executes if "shoe_size_map" in c[0])
    assert params == {"size": Decimal("9.5")}


def test_recommend_no_target_yields_target_null():
    survey = _survey_tuple(goal_x_target=None, goal_y_target=None)
    assert _post_recommend(_recommend_conn(survey=survey)).json()["target"] is None


def test_recommend_target_is_an_xy_object_when_set():
    assert _post_recommend(_recommend_conn()).json()["target"] == {"x": 0.5, "y": 0.5}


def test_recommend_gated_out_and_terms_are_reported():
    body = _post_recommend(_recommend_conn()).json()
    assert (body["terms"], body["gated_out"]) == (
        {"fit": True, "style": True, "budget": True},
        {"over_budget": 0, "size_unavailable": 0, "unplaced": 0},
    )


def test_recommend_result_keys_include_every_quadrant_shoe_field():
    from app.api.routes.quadrant import QuadrantShoeOut

    result = _post_recommend(_recommend_conn()).json()["results"][0]
    assert set(QuadrantShoeOut.model_fields) <= set(result)


def test_recommend_result_has_the_scoring_fields():
    result = _post_recommend(_recommend_conn()).json()["results"][0]
    assert {"msrp_usd", "price_unknown", "fit_score", "style_score", "budget_score",
            "total_score", "confidence", "confidence_label", "rank", "warnings"} <= set(result)


def test_recommend_unused_term_scores_are_null():
    survey = _survey_tuple(foot_width=None, budget_cap_usd=None)
    result = _post_recommend(_recommend_conn(survey=survey)).json()["results"][0]
    assert (result["fit_score"], result["budget_score"]) == (None, None)


def test_recommend_scorer_value_error_is_the_masked_500():
    survey = _survey_tuple(goal_x_target=Decimal("0.5"), goal_y_target=None)
    resp = _post_recommend(_recommend_conn(survey=survey), raise_server_exceptions=False)
    assert (resp.status_code, resp.json()) == (500, {"detail": "could not complete the request"})


def test_recommend_scorer_error_never_commits():
    survey = _survey_tuple(goal_x_target=Decimal("0.5"), goal_y_target=None)
    conn = _recommend_conn(survey=survey)
    _post_recommend(conn, raise_server_exceptions=False)
    assert conn.commits == 0


def test_recommend_invalid_body_never_opens_a_database_connection(real_get_conn):
    opened, _ = real_get_conn
    resp = TestClient(create_app()).post("/recommend", json={"survey_token": "bad token!"})
    assert (resp.status_code, opened) == (422, [])


def test_recommend_scorer_result_failing_response_validation_never_commits(monkeypatch):
    import app.api.routes.recommend as route

    real = route.score.recommend

    def corrupt(survey, shoes, size_rows):
        ranking = real(survey, shoes, size_rows)
        bad = dict(ranking.results[0], total_score=float("nan"))
        return route.score.Ranking(
            ranking.scorer_version, ranking.target, ranking.terms,
            ranking.gated_out, ranking.warnings, (bad,))

    monkeypatch.setattr(route.score, "recommend", corrupt)
    conn = _recommend_conn()
    resp = _post_recommend(conn, raise_server_exceptions=False)
    assert (resp.status_code, conn.commits) == (500, 0)


def test_recommend_empty_results_still_delete_with_an_empty_kept_list():
    conn = _recommend_conn(shoes=[_shoe_tuple(msrp_usd=Decimal("999.00"))])
    _post_recommend(conn)
    sql, params = conn.executes[-1]
    assert (sql.startswith("DELETE FROM recommendation"), params["kept"], conn.executemanys) == (
        True, [], [])


def test_recommend_404_and_422_responses_are_described_in_openapi():
    responses = create_app().openapi()["paths"]["/recommend"]["post"]["responses"]
    assert (responses["404"]["description"], responses["422"]["description"]) == (
        "No survey exists for the given survey_token.",
        "Body is not exactly {\"survey_token\": <token>}, or is not valid JSON.",
    )


def test_recommend_operational_error_is_503_with_the_generic_body():
    conn = _ScriptedConn(raise_on_execute=psycopg.OperationalError("conn refused host=db"))
    resp = _post_recommend(conn, raise_server_exceptions=False)
    assert (resp.status_code, resp.json()) == (503, {"detail": "database unavailable"})


def test_recommend_503_body_does_not_contain_the_token():
    conn = _ScriptedConn(raise_on_execute=psycopg.OperationalError("boom"))
    assert RECOMMEND_TOKEN not in _post_recommend(conn, raise_server_exceptions=False).text


def test_recommend_failure_never_commits():
    conn = _ScriptedConn(raise_on_execute=psycopg.OperationalError("boom"))
    _post_recommend(conn, raise_server_exceptions=False)
    assert conn.commits == 0


def test_recommend_token_is_absent_from_logs(caplog):
    conn = _ScriptedConn(raise_on_execute=psycopg.OperationalError(f"boom {RECOMMEND_TOKEN}"))
    with caplog.at_level("DEBUG"):
        _post_recommend(conn, raise_server_exceptions=False)
        _client_with_overrides(conn=_ScriptedConn(fetchones=[None])).post(
            "/recommend", json={"survey_token": RECOMMEND_TOKEN})
    assert RECOMMEND_TOKEN not in caplog.text


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


def test_db_post_survey_stores_the_target_derived_from_goal(live_client, db_conn):
    """Cleanup is unconditional for the same reason as the persistence test
    above: the row is committed before the response arrives."""
    payload = {"discipline": "trad", "terrain": "crack", "level": "elite", "goal": 0.5}
    expected_x, _ = P.target_quadrant("trad", "crack", "elite", 0.5)

    token = None
    try:
        resp = live_client.post("/survey", json=payload)
        token = resp.json().get("survey_token") if resp.status_code == 201 else None
        with db_conn.cursor() as cur:
            cur.execute("SELECT goal_x_target FROM user_survey WHERE survey_token = %s", (token,))
            stored = cur.fetchone()
        assert float(stored[0]) == pytest.approx(expected_x)
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


def test_db_get_quadrant_length_matches_live_count_of_placed_shoes(live_client, db_conn):
    body = live_client.get("/quadrant").json()
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM shoe WHERE quadrant_x_prior IS NOT NULL")
        (count,) = cur.fetchone()
    assert len(body) == count


@pytest.fixture()
def seeded_db(db_conn):
    """Anchor assertions are meaningless against an empty `shoe` table (a
    fresh migrated-but-unseeded DB), so skip rather than fail there."""
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM shoe")
        (count,) = cur.fetchone()
    if count == 0:
        pytest.skip("shoe table is empty; run the seed to exercise anchor assertions")


def test_db_get_quadrant_flags_exactly_five_anchors(live_client, seeded_db):
    body = live_client.get("/quadrant").json()
    assert sum(item["is_anchor"] for item in body) == 5


def test_db_get_quadrant_each_anchor_sits_in_its_section_3_quadrant(live_client, seeded_db):
    body = live_client.get("/quadrant").json()
    actual = {
        (i["brand"], i["model"], i["version"]): i["quadrant"] for i in body if i["is_anchor"]
    }
    assert actual == ANCHORS


# --- POST /recommend, DB-backed ---------------------------------------------

def _create_survey_row(db_conn, **overrides):
    """Insert a survey through the store (the only supported writer) and
    commit, so the app's own connection can see it."""
    row, errors = ST.build_survey_row(
        {"discipline": "sport", "terrain": "overhang", "level": "advanced",
         "budget_cap_usd": 400, **overrides}, A.PostgresCatalog(db_conn))
    assert errors == []
    return ST.insert_survey(db_conn, row)


def _recommendation_rows(db_conn, token):
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT r.shoe_id::text, r.total_score, r.scorer_version, r.rank, "
            "r.accepted, r.feedback_at FROM recommendation r "
            "JOIN user_survey s ON s.id = r.survey_id WHERE s.survey_token = %s "
            "ORDER BY r.rank", (token,))
        rows = cur.fetchall()
    db_conn.rollback()
    return rows


def _delete_survey_row(db_conn, token):
    # recommendation rows go with it: ON DELETE CASCADE.
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM user_survey WHERE survey_token = %s", (token,))
    db_conn.commit()


def test_db_recommend_persists_one_row_per_active_placed_in_budget_shoe(live_client, db_conn, seeded_db):
    token = _create_survey_row(db_conn)
    try:
        body = live_client.post("/recommend", json={"survey_token": token}).json()
        with db_conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM shoe WHERE status = 'active' "
                "AND quadrant_x_prior IS NOT NULL AND (msrp_usd IS NULL OR msrp_usd <= 400)")
            (expected,) = cur.fetchone()
        assert len(_recommendation_rows(db_conn, token)) == expected == len(body["results"])
    finally:
        _delete_survey_row(db_conn, token)


def test_db_recommend_re_request_leaves_the_row_count_unchanged(live_client, db_conn, seeded_db):
    token = _create_survey_row(db_conn)
    try:
        live_client.post("/recommend", json={"survey_token": token})
        first = len(_recommendation_rows(db_conn, token))
        live_client.post("/recommend", json={"survey_token": token})
        assert len(_recommendation_rows(db_conn, token)) == first
    finally:
        _delete_survey_row(db_conn, token)


def test_db_recommend_re_request_preserves_feedback_set_between_calls(live_client, db_conn, seeded_db):
    token = _create_survey_row(db_conn)
    try:
        first = live_client.post("/recommend", json={"survey_token": token}).json()
        shoe_id = first["results"][0]["id"]
        with db_conn.cursor() as cur:
            cur.execute(
                "UPDATE recommendation SET accepted = TRUE, feedback_at = now() "
                "WHERE shoe_id = %s AND survey_id = (SELECT id FROM user_survey WHERE survey_token = %s)",
                (shoe_id, token))
        db_conn.commit()
        live_client.post("/recommend", json={"survey_token": token})
        row = next(r for r in _recommendation_rows(db_conn, token) if r[0] == shoe_id)
        assert (row[4], row[5] is not None) == (True, True)
    finally:
        _delete_survey_row(db_conn, token)


def test_db_recommend_row_with_feedback_keeps_its_rank_scores_and_version(live_client, db_conn, seeded_db):
    token = _create_survey_row(db_conn)
    try:
        shoe_id = live_client.post("/recommend", json={"survey_token": token}).json()["results"][0]["id"]
        # Values no re-score could produce, so any rewrite shows.
        with db_conn.cursor() as cur:
            cur.execute(
                "UPDATE recommendation SET rank = 999, fit_score = 0.1111, style_score = 0.2222, "
                "budget_score = 0.3333, total_score = 0.4444, confidence = 0.5555, "
                "scorer_version = 'shown-earlier', accepted = TRUE, feedback_at = now() "
                "WHERE shoe_id = %s AND survey_id = (SELECT id FROM user_survey WHERE survey_token = %s)",
                (shoe_id, token))
        db_conn.commit()
        live_client.post("/recommend", json={"survey_token": token})
        with db_conn.cursor() as cur:
            cur.execute(
                "SELECT rank, fit_score::text, style_score::text, budget_score::text, "
                "total_score::text, confidence::text, scorer_version FROM recommendation "
                "WHERE shoe_id = %s AND survey_id = (SELECT id FROM user_survey WHERE survey_token = %s)",
                (shoe_id, token))
            row = cur.fetchone()
        db_conn.rollback()
        assert row == (999, "0.1111", "0.2222", "0.3333", "0.4444", "0.5555", "shown-earlier")
    finally:
        _delete_survey_row(db_conn, token)


def test_db_recommend_shoe_gated_out_after_a_cap_change_is_deleted_without_feedback(live_client, db_conn, seeded_db):
    token = _create_survey_row(db_conn)
    try:
        first = live_client.post("/recommend", json={"survey_token": token}).json()
        priced = [r for r in first["results"] if r["msrp_usd"] is not None]
        dearest = max(priced, key=lambda r: r["msrp_usd"])
        with db_conn.cursor() as cur:
            cur.execute("UPDATE user_survey SET budget_cap_usd = %s WHERE survey_token = %s",
                        (dearest["msrp_usd"] - 1, token))
        db_conn.commit()
        live_client.post("/recommend", json={"survey_token": token})
        assert dearest["id"] not in [r[0] for r in _recommendation_rows(db_conn, token)]
    finally:
        _delete_survey_row(db_conn, token)


def test_db_recommend_persisted_total_score_equals_the_response(live_client, db_conn, seeded_db):
    token = _create_survey_row(db_conn)
    try:
        body = live_client.post("/recommend", json={"survey_token": token}).json()
        stored = {r[0]: float(r[1]) for r in _recommendation_rows(db_conn, token)}
        assert stored == {r["id"]: r["total_score"] for r in body["results"]}
    finally:
        _delete_survey_row(db_conn, token)


def test_db_recommend_persisted_scorer_version_is_v0_slice(live_client, db_conn, seeded_db):
    token = _create_survey_row(db_conn)
    try:
        live_client.post("/recommend", json={"survey_token": token})
        assert {r[2] for r in _recommendation_rows(db_conn, token)} == {"v0-slice"}
    finally:
        _delete_survey_row(db_conn, token)


def test_db_recommend_cap_below_every_priced_shoe_leaves_only_unpriced_rows(live_client, db_conn, seeded_db):
    """NULL-MSRP shoes are never price-gated, so the seeded catalogue cannot
    produce an empty ranking; the empty case is pinned hermetically."""
    token = _create_survey_row(db_conn)
    try:
        live_client.post("/recommend", json={"survey_token": token})
        with db_conn.cursor() as cur:
            cur.execute("UPDATE user_survey SET budget_cap_usd = 0.01 WHERE survey_token = %s", (token,))
        db_conn.commit()
        live_client.post("/recommend", json={"survey_token": token})
        stored = {r[0] for r in _recommendation_rows(db_conn, token)}
        with db_conn.cursor() as cur:
            cur.execute("SELECT id::text FROM shoe WHERE status = 'active' "
                        "AND quadrant_x_prior IS NOT NULL AND msrp_usd IS NULL")
            unpriced = {r[0] for r in cur.fetchall()}
        db_conn.rollback()
        assert stored == unpriced
    finally:
        _delete_survey_row(db_conn, token)
