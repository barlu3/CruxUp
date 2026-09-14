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
# Quota
# --------------------------------------------------------------------------

def test_quota_checked_before_call_not_after():
    """A budget too small for even one search must make zero API calls."""
    api = FakeAPI()
    src = C.YouTubeSource(api_key="k", fetch=api, unit_budget=50)  # search costs 100
    docs = src.collect("query", limit=10)

    assert docs == []
    assert api.calls == [], "spent quota it did not have"
    assert src.units_used == 0


def test_quota_accounting_matches_documented_costs():
    api = FakeAPI(
        search=_search_response("vid1", "vid2"),
        comments={
            "vid1": {"items": [_comment("c1", "one")]},
            "vid2": {"items": [_comment("c2", "two")]},
        },
    )
    src = C.YouTubeSource(api_key="k", fetch=api)
    src.collect("query", limit=10)

    expected = C.YouTubeSource.COST_SEARCH + 2 * C.YouTubeSource.COST_COMMENT_THREADS
    assert src.units_used == expected


def test_partial_results_kept_when_quota_runs_out_midway():
    """Documents already collected must survive a mid-run quota exhaustion."""
    api = FakeAPI(
        search=_search_response("vid1", "vid2", "vid3"),
        comments={
            v: {"items": [_comment(f"c{v}", "text")]} for v in ("vid1", "vid2", "vid3")
        },
    )
    # room for the search (100) plus exactly two commentThreads calls
    src = C.YouTubeSource(api_key="k", fetch=api, unit_budget=102)
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


def test_unavailable_sources_report_reason_without_raising():
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
