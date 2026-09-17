"""[W1-0b] Collector tests.

No network. The YouTube adapter takes an injectable transport, so every API
response here is a fixture. What these actually pin down:

  - quota is enforced BEFORE a call, not after (an overrun costs a day)
  - author display names never reach storage; channel IDs are hashed
  - collection is idempotent across restarts
  - a video with comments disabled does not abort the run
  - a malformed timestamp does not discard the document
"""

from __future__ import annotations

import sys
from datetime import timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "scraping"))
import collector as C  # noqa: E402


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

def _search_response(*video_ids):
    return {
        "items": [
            {"id": {"videoId": v}, "snippet": {"title": f"Review of {v}"}}
            for v in video_ids
        ]
    }


def _comment(cid, text, published="2026-03-04T11:22:33Z", channel="UC_abc123"):
    return {
        "id": cid,
        "snippet": {
            "topLevelComment": {
                "snippet": {
                    "textDisplay": text,
                    "publishedAt": published,
                    "likeCount": 7,
                    "authorDisplayName": "RealPersonName",
                    "authorChannelId": {"value": channel},
                }
            }
        },
    }


class FakeAPI:
    """Scripted transport. Records calls so quota accounting can be asserted."""

    def __init__(self, search=None, comments=None, fail_comments_for=()):
        self.search = search or _search_response("vid1")
        self.comments = comments or {}
        self.fail_comments_for = set(fail_comments_for)
        self.calls = []

    def __call__(self, url, params):
        self.calls.append((url.rsplit("/", 1)[-1], params))
        if url.endswith("/search"):
            return self.search
        if url.endswith("/commentThreads"):
            vid = params["videoId"]
            if vid in self.fail_comments_for:
                raise RuntimeError("YouTube API 403: commentsDisabled")
            return self.comments.get(vid, {"items": []})
        raise AssertionError(f"unexpected endpoint {url}")


@pytest.fixture
def store(tmp_path):
    return C.LandingStore(tmp_path / "t.sqlite3")


TEST_SALT = "0123456789abcdef" * 4  # 64 chars; synthetic, test-only


@pytest.fixture(autouse=True)
def author_salt(monkeypatch):
    """Every test hashes authors, and hashing now refuses to run without a key."""
    monkeypatch.setenv(C.SALT_ENV, TEST_SALT)


# --------------------------------------------------------------------------
# PII
# --------------------------------------------------------------------------

def test_author_display_name_never_stored():
    api = FakeAPI(comments={"vid1": {"items": [_comment("c1", "great shoe")]}})
    src = C.YouTubeSource(api_key="k", fetch=api)
    docs = src.collect("query", limit=5)

    assert len(docs) == 1
    blob = repr(docs[0])
    assert "RealPersonName" not in blob, "display name leaked into the document"
    assert "UC_abc123" not in blob, "raw channel id leaked; it must be hashed"
    assert docs[0].author_hash and len(docs[0].author_hash) == 64


def test_author_hash_is_deterministic_and_distinct():
    assert C._hash_author("a") == C._hash_author("a")
    assert C._hash_author("a") != C._hash_author("b")
    assert C._hash_author(None) is None
    assert C._hash_author("") is None


# --------------------------------------------------------------------------
# Author salt (read at hash time; no public default)
# --------------------------------------------------------------------------

def test_hashing_refuses_without_a_salt(monkeypatch):
    monkeypatch.delenv(C.SALT_ENV, raising=False)
    with pytest.raises(C.MissingAuthorSalt):
        C._hash_author("UC_abc123")


@pytest.mark.parametrize("weak", ["cruxup-dev-salt", "short", ""])
def test_burned_or_weak_salts_are_rejected(monkeypatch, weak):
    monkeypatch.setenv(C.SALT_ENV, weak)
    with pytest.raises(C.MissingAuthorSalt):
        C._hash_author("UC_abc123")


def test_salt_is_read_at_hash_time_not_import_time(monkeypatch):
    """The original bug: a salt set after import (as .env loading does) was ignored."""
    monkeypatch.setenv(C.SALT_ENV, "a" * 64)
    first = C._hash_author("UC_abc123")
    monkeypatch.setenv(C.SALT_ENV, "b" * 64)
    assert C._hash_author("UC_abc123") != first, "hash ignored a salt set after import"


def test_hash_is_keyed_so_the_raw_id_alone_cannot_reproduce_it():
    import hashlib
    h = C._hash_author("UC_abc123")
    assert h != hashlib.sha256(b"UC_abc123").hexdigest()
    assert h != hashlib.sha256(b"cruxup-dev-salt:UC_abc123").hexdigest(), \
        "still reproducible with the old public salt"


# --------------------------------------------------------------------------
# Quota: separate buckets, persisted, reserved before the request
# --------------------------------------------------------------------------

class FixedClock:
    def __init__(self, day):
        from datetime import datetime
        self.now = datetime.fromisoformat(f"{day}T12:00:00")
    def __call__(self):
        return self.now


def test_exhausted_search_bucket_makes_zero_calls():
    api = FakeAPI()
    src = C.YouTubeSource(api_key="k", fetch=api, search_limit=0)
    assert src.collect("query", limit=10) == []
    assert api.calls == [], "spent quota it did not have"


def test_search_and_units_are_separate_buckets():
    """Per Google: search.list is its own 100/day bucket at cost 1, not 100 units."""
    api = FakeAPI(
        search=_search_response("vid1", "vid2"),
        comments={"vid1": {"items": [_comment("c1", "one")]},
                  "vid2": {"items": [_comment("c2", "two")]}},
    )
    ledger = C.QuotaLedger.in_memory()
    C.YouTubeSource(api_key="k", fetch=api, quota=ledger).collect("query", limit=10)

    assert ledger.used(C.YouTubeSource.SEARCH_BUCKET) == 1
    assert ledger.used(C.YouTubeSource.UNITS_BUCKET) == 2, \
        "search must not be charged against the shared unit pool"


def test_exhausted_search_bucket_does_not_block_comment_units():
    ledger = C.QuotaLedger.in_memory()
    for _ in range(100):
        ledger.reserve(C.YouTubeSource.SEARCH_BUCKET, 1, 100)
    with pytest.raises(C.QuotaExceeded):
        ledger.reserve(C.YouTubeSource.SEARCH_BUCKET, 1, 100)
    ledger.reserve(C.YouTubeSource.UNITS_BUCKET, 1, 10_000)  # must not raise


def test_failed_request_still_consumes_quota():
    """Google charges quota even for invalid requests; the ledger must agree."""
    def failing_fetch(url, params):
        raise RuntimeError("YouTube API 400: bad request")
    ledger = C.QuotaLedger.in_memory()
    src = C.YouTubeSource(api_key="k", fetch=failing_fetch, quota=ledger)
    with pytest.raises(RuntimeError):
        src._search_videos("query")
    assert ledger.used(C.YouTubeSource.SEARCH_BUCKET) == 1


def test_quota_persists_across_processes(tmp_path):
    """A second run on the same day must resume from the stored count, not zero."""
    import sqlite3
    db = tmp_path / "q.sqlite3"
    clock = FixedClock("2026-09-16")

    first = C.QuotaLedger(sqlite3.connect(db), clock=clock)
    for _ in range(3):
        first.reserve(C.YouTubeSource.SEARCH_BUCKET, 1, 5)
    first.conn.close()

    second = C.QuotaLedger(sqlite3.connect(db), clock=clock)  # fresh "process"
    assert second.used(C.YouTubeSource.SEARCH_BUCKET) == 3
    second.reserve(C.YouTubeSource.SEARCH_BUCKET, 1, 5)
    second.reserve(C.YouTubeSource.SEARCH_BUCKET, 1, 5)
    with pytest.raises(C.QuotaExceeded):
        second.reserve(C.YouTubeSource.SEARCH_BUCKET, 1, 5)


def test_quota_resets_on_a_new_pacific_day(tmp_path):
    import sqlite3
    conn = sqlite3.connect(tmp_path / "q.sqlite3")
    C.QuotaLedger(conn, clock=FixedClock("2026-09-16")).reserve("youtube.search", 1, 1)
    with pytest.raises(C.QuotaExceeded):
        C.QuotaLedger(conn, clock=FixedClock("2026-09-16")).reserve("youtube.search", 1, 1)
    C.QuotaLedger(conn, clock=FixedClock("2026-09-17")).reserve("youtube.search", 1, 1)


def test_partial_results_kept_when_quota_runs_out_midway():
    """Documents already collected must survive a mid-run quota exhaustion."""
    api = FakeAPI(
        search=_search_response("vid1", "vid2", "vid3"),
        comments={
            v: {"items": [_comment(f"c{v}", "text")]} for v in ("vid1", "vid2", "vid3")
        },
    )
    # room for exactly two commentThreads calls in the unit bucket
    src = C.YouTubeSource(api_key="k", fetch=api, unit_limit=2)
    docs = src.collect("query", limit=10)

    assert len(docs) == 2, "should keep what it got before the budget ran out"


# --------------------------------------------------------------------------
# Robustness
# --------------------------------------------------------------------------

def test_comments_disabled_does_not_abort_the_run():
    api = FakeAPI(
        search=_search_response("vid1", "vid2"),
        comments={"vid2": {"items": [_comment("c2", "still collected")]}},
        fail_comments_for=["vid1"],
    )
    src = C.YouTubeSource(api_key="k", fetch=api)
    docs = src.collect("query", limit=10)

    assert len(docs) == 1
    assert docs[0].body == "still collected"


def test_malformed_timestamp_keeps_the_document():
    api = FakeAPI(
        comments={"vid1": {"items": [_comment("c1", "text", published="not-a-date")]}}
    )
    src = C.YouTubeSource(api_key="k", fetch=api)
    docs = src.collect("query", limit=5)

    assert len(docs) == 1, "a bad timestamp must not discard an otherwise-good document"
    assert docs[0].created_utc is None


def test_good_timestamp_parsed_as_utc():
    api = FakeAPI(comments={"vid1": {"items": [_comment("c1", "text")]}})
    docs = C.YouTubeSource(api_key="k", fetch=api).collect("q", limit=5)
    assert docs[0].created_utc.tzinfo is not None
    assert docs[0].created_utc.astimezone(timezone.utc).year == 2026


def test_empty_comment_bodies_skipped():
    api = FakeAPI(
        comments={"vid1": {"items": [_comment("c1", "   "), _comment("c2", "real")]}}
    )
    docs = C.YouTubeSource(api_key="k", fetch=api).collect("q", limit=5)
    assert [d.body for d in docs] == ["real"]


def test_pagination_stops_at_limit():
    page = {
        "items": [_comment(f"c{i}", f"text {i}") for i in range(100)],
        "nextPageToken": "PAGE2",
    }
    api = FakeAPI(comments={"vid1": page})
    src = C.YouTubeSource(api_key="k", fetch=api, videos_per_query=1)
    docs = src.collect("q", limit=10)
    assert len(docs) == 10, "must respect the limit rather than draining every page"


# --------------------------------------------------------------------------
# Store
# --------------------------------------------------------------------------

def test_insert_is_idempotent(store):
    api = FakeAPI(comments={"vid1": {"items": [_comment("c1", "a"), _comment("c2", "b")]}})
    docs = C.YouTubeSource(api_key="k", fetch=api).collect("q", limit=5)

    assert store.insert(docs) == 2
    assert store.insert(docs) == 0, "re-running an identical collection must insert nothing"
    assert store.insert(docs[:1]) == 0


def test_unavailable_sources_report_reason_without_raising(monkeypatch):
    # YouTubeSource(api_key=None) and RedditSource() fall back to ambient
    # credentials, so a configured shell or CI environment would flip this.
    for var in ("YOUTUBE_API_KEY", "REDDIT_CLIENT_ID",
                "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT"):
        monkeypatch.delenv(var, raising=False)
    for src in (C.YouTubeSource(api_key=None), C.ForumSource(), C.RedditSource()):
        ok, reason = src.available()
        assert ok is False
        assert reason and isinstance(reason, str)


def test_reddit_stays_unavailable_without_credentials(monkeypatch):
    """D11: Reddit must not become load-bearing by accident."""
    for var in ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT"):
        monkeypatch.delenv(var, raising=False)
    ok, reason = C.RedditSource().available()
    assert ok is False
    assert "approval" in reason.lower()


def test_collector_skips_unavailable_sources(store):
    api = FakeAPI(comments={"vid1": {"items": [_comment("c1", "text")]}})
    sources = [C.YouTubeSource(api_key="k", fetch=api), C.ForumSource(), C.RedditSource()]
    totals = C.Collector(sources, store).run(["q"], limit=5)

    assert totals == {"youtube": 1}, "unavailable sources must be skipped, not fatal"


def test_daily_volume_is_queryable(store):
    api = FakeAPI(comments={"vid1": {"items": [_comment("c1", "text")]}})
    docs = C.YouTubeSource(api_key="k", fetch=api).collect("q", limit=5)
    store.insert(docs)

    rows = store.daily_volume()
    assert len(rows) == 1
    day, source, count = rows[0]
    assert source == "youtube" and count == 1 and len(day) == 10
