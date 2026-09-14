"""[W1-0b] Source-agnostic corpus collector.

Why this shape
--------------
D11 (timeline.md section 10.0) changed what W1-0 can be. v3 assumed you could
register a Reddit app and start collecting on day one. You cannot: self-service
registration is closed and every OAuth client goes through manual approval,
reported at 2-4 weeks with a real chance of silent rejection.

So the collector is written source-agnostic from the first commit. Reddit is
one adapter among several, added behind the same interface if and when approval
lands (W1-0c). Nothing downstream knows or cares which sources are live.

The underlying urgency is unchanged: Pushshift is dead, there is no historical
bulk, and the corpus only accrues forward in wall-clock time. Every idle day is
unrecoverable. That is why this runs now against sources that need no approval,
rather than waiting.

Storage
-------
Writes to a local landing table, NOT to the section 8.2 `mention` schema. That
schema is W0-1b and is gated on W0-0. Raw payloads land here verbatim; W1-full
normalises them later. Keeping raw means a normalisation bug is recoverable
without re-collecting, which matters when re-collection is impossible.

PII
---
Author identifiers are hashed at write time and the raw value is never stored.
See `_hash_author`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sqlite3
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("collector")

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "corpus_landing.sqlite3"

# A per-run salt would make hashes non-comparable across runs, so the salt is
# fixed per deployment. It is not a secret in the cryptographic sense -- it
# exists so a stored hash cannot be trivially reversed against a username list.
AUTHOR_SALT = os.environ.get("CRUXUP_AUTHOR_SALT", "cruxup-dev-salt")


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RawDocument:
    """One collected item, before any normalisation.

    `external_id` must be stable and unique within a source -- it is what makes
    collection idempotent across restarts.
    """

    source: str
    external_id: str
    body: str
    permalink: str
    created_utc: datetime | None
    author_hash: str | None
    payload: dict = field(default_factory=dict)


def _hash_author(author: str | None) -> str | None:
    """Hash an author identifier. The raw value never reaches storage."""
    if not author:
        return None
    return hashlib.sha256(f"{AUTHOR_SALT}:{author}".encode()).hexdigest()


def _parse_iso8601(value: str | None) -> datetime | None:
    """Parse an API timestamp. Returns None rather than raising.

    A malformed timestamp must not discard an otherwise-usable document -- the
    recency weight r_m (section 7.4) degrades gracefully without one, but a
    lost document is unrecoverable.
    """
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        log.debug("unparseable timestamp: %r", value)
        return None


# ---------------------------------------------------------------------------
# Source adapters
# ---------------------------------------------------------------------------

class Source(ABC):
    """A corpus source.

    Adapters are responsible for their own rate limiting and for declaring
    whether they are currently usable. `available()` returning False is a normal
    condition -- an un-approved Reddit app, a missing API key -- and must not
    raise: the collector runs whatever sources are live and skips the rest.
    """

    name: str

    @abstractmethod
    def available(self) -> tuple[bool, str]:
        """(usable, human-readable reason). Never raises."""

    @abstractmethod
    def collect(self, query: str, limit: int) -> list[RawDocument]:
        """Fetch up to `limit` documents matching `query`."""


class QuotaExceeded(RuntimeError):
    """The daily API quota is spent. Not retryable until it resets."""


class YouTubeSource(Source):
    """YouTube Data API v3.

    Primary source under D11 -- needs only an API key, no approval queue.

    Caveat carried from section 10.1: official captions require the *video
    owner's* OAuth, so third-party transcripts are not reachable through the
    sanctioned route. This adapter collects video metadata and comments, which
    are reachable. Transcript collection is deliberately NOT implemented here --
    the only practical route is unofficial, and that is a decision to take
    explicitly rather than smuggle into a collector.

    Quota
    -----
    The default allowance is 10,000 units/day. search.list costs 100 units;
    commentThreads.list costs 1. So a run that searches 10 queries and pulls
    comments from 5 videos each costs 10*100 + ~50 = ~1,050 units. The budget
    is tracked in `units_used` and enforced before every call, because
    overrunning it returns 403 for the rest of the day and silently ends
    collection -- and a lost day of collection is not recoverable (the
    Pushshift lesson, section 10.0).

    Transport is injected so the adapter is testable without network access.
    """

    name = "youtube"

    API = "https://www.googleapis.com/youtube/v3"
    COST_SEARCH = 100
    COST_COMMENT_THREADS = 1
    DAILY_UNIT_BUDGET = 10_000

    def __init__(
        self,
        api_key: str | None = None,
        fetch=None,
        unit_budget: int = DAILY_UNIT_BUDGET,
        videos_per_query: int = 5,
    ):
        self.api_key = api_key or os.environ.get("YOUTUBE_API_KEY")
        self._fetch = fetch or self._http_get
        self.unit_budget = unit_budget
        self.units_used = 0
        self.videos_per_query = videos_per_query

    def available(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "YOUTUBE_API_KEY not set"
        return True, "ok"

    # -- transport ---------------------------------------------------------

    @staticmethod
    def _http_get(url: str, params: dict) -> dict:
        """Default transport. Stdlib only -- no extra dependency for one GET."""
        import urllib.error
        import urllib.parse
        import urllib.request

        qs = urllib.parse.urlencode(params)
        req = urllib.request.Request(f"{url}?{qs}", headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            if exc.code == 403 and "quota" in body.lower():
                raise QuotaExceeded(body[:200]) from exc
            raise RuntimeError(f"YouTube API {exc.code}: {body[:200]}") from exc

    def _call(self, endpoint: str, cost: int, **params) -> dict:
        if self.units_used + cost > self.unit_budget:
            raise QuotaExceeded(
                f"would exceed unit budget ({self.units_used}+{cost} > {self.unit_budget})"
            )
        params["key"] = self.api_key
        result = self._fetch(f"{self.API}/{endpoint}", params)
        self.units_used += cost
        return result

    # -- collection --------------------------------------------------------

    def _search_videos(self, query: str) -> list[tuple[str, str]]:
        """(video_id, title) for videos matching `query`."""
        data = self._call(
            "search",
            self.COST_SEARCH,
            part="snippet",
            q=query,
            type="video",
            maxResults=min(self.videos_per_query, 50),
            relevanceLanguage="en",
        )
        out = []
        for item in data.get("items", []):
            vid = (item.get("id") or {}).get("videoId")
            if vid:
                out.append((vid, (item.get("snippet") or {}).get("title", "")))
        return out

    def _comments(self, video_id: str, limit: int) -> list[RawDocument]:
        """Top-level comments on one video, paginating until `limit`."""
        docs: list[RawDocument] = []
        page_token = None

        while len(docs) < limit:
            params = dict(
                part="snippet",
                videoId=video_id,
                maxResults=min(100, limit - len(docs)),
                textFormat="plainText",
                order="relevance",
            )
            if page_token:
                params["pageToken"] = page_token

            try:
                data = self._call("commentThreads", self.COST_COMMENT_THREADS, **params)
            except QuotaExceeded:
                raise
            except RuntimeError as exc:
                # Comments disabled on a video is routine, not a failure.
                log.debug("comments unavailable for %s: %s", video_id, exc)
                break

            for item in data.get("items", []):
                top = (
                    (item.get("snippet") or {})
                    .get("topLevelComment", {})
                    .get("snippet", {})
                )
                body = (top.get("textDisplay") or "").strip()
                if not body:
                    continue
                docs.append(
                    RawDocument(
                        source=self.name,
                        external_id=item.get("id", ""),
                        body=body,
                        permalink=(
                            f"https://www.youtube.com/watch?v={video_id}"
                            f"&lc={item.get('id','')}"
                        ),
                        created_utc=_parse_iso8601(top.get("publishedAt")),
                        author_hash=_hash_author(
                            (top.get("authorChannelId") or {}).get("value")
                        ),
                        payload={
                            "video_id": video_id,
                            "like_count": top.get("likeCount"),
                            # authorDisplayName is deliberately NOT stored: it is
                            # the PII the hash exists to avoid keeping.
                        },
                    )
                )

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return docs[:limit]

    def collect(self, query: str, limit: int) -> list[RawDocument]:
        docs: list[RawDocument] = []
        try:
            videos = self._search_videos(query)
        except QuotaExceeded:
            log.warning("youtube quota exhausted during search for '%s'", query)
            return []

        per_video = max(1, limit // len(videos)) if videos else limit
        for video_id, title in videos:
            if len(docs) >= limit:
                break
            try:
                got = self._comments(video_id, min(per_video, limit - len(docs)))
            except QuotaExceeded:
                log.warning("youtube quota exhausted after %d docs", len(docs))
                break
            log.debug("  %s '%s': %d comments", video_id, title[:40], len(got))
            docs.extend(got)
        return docs


class ForumSource(Source):
    """Climbing forums (Mountain Project, UKClimbing).

    Secondary source under D11. No API and no approval queue, but each site's
    robots.txt and terms govern -- check both before enabling, and rate-limit
    conservatively. Forum threads skew toward longer, more considered posts than
    comment sections, which is better signal per document for section 7.4.
    """

    name = "forum"

    def __init__(self, base_urls: list[str] | None = None):
        self.base_urls = base_urls or []

    def available(self) -> tuple[bool, str]:
        if not self.base_urls:
            return False, "no forum base URLs configured"
        return True, "ok"

    def collect(self, query: str, limit: int) -> list[RawDocument]:
        raise NotImplementedError(
            "Forum adapter not yet implemented. Before writing it: confirm "
            "robots.txt and terms for each target site, and set a crawl delay "
            "well below whatever they permit."
        )


class RedditSource(Source):
    """Reddit via PRAW. Gated on W0-0 approval (D11).

    Deliberately last and deliberately optional. `available()` returns False
    until credentials exist, so the collector runs without it and lights it up
    when approval lands -- no code change, no downstream impact.
    """

    name = "reddit"

    def __init__(self):
        self.client_id = os.environ.get("REDDIT_CLIENT_ID")
        self.client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
        self.user_agent = os.environ.get("REDDIT_USER_AGENT")

    def available(self) -> tuple[bool, str]:
        if not all([self.client_id, self.client_secret, self.user_agent]):
            return False, "Reddit credentials absent (W0-0 approval pending)"
        return True, "ok"

    def collect(self, query: str, limit: int) -> list[RawDocument]:
        raise NotImplementedError(
            "Reddit adapter is W1-0c -- implement only once the free "
            "non-commercial application is approved. Free tier is "
            "non-commercial only; commercial use needs separate written "
            "approval (section 10.0)."
        )


# ---------------------------------------------------------------------------
# Landing store
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_document (
    source        TEXT    NOT NULL,
    external_id   TEXT    NOT NULL,
    body          TEXT    NOT NULL,
    permalink     TEXT,
    created_utc   TEXT,
    author_hash   TEXT,
    payload_json  TEXT,
    collected_at  TEXT    NOT NULL,
    PRIMARY KEY (source, external_id)
);
CREATE INDEX IF NOT EXISTS raw_document_collected_idx ON raw_document (collected_at);
CREATE INDEX IF NOT EXISTS raw_document_source_idx    ON raw_document (source);

CREATE TABLE IF NOT EXISTS collection_run (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    source       TEXT NOT NULL,
    query        TEXT,
    fetched      INTEGER NOT NULL DEFAULT 0,
    inserted     INTEGER NOT NULL DEFAULT 0,
    error        TEXT
);
"""


class LandingStore:
    def __init__(self, path: Path = DEFAULT_DB):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def insert(self, docs: list[RawDocument]) -> int:
        """Insert documents, ignoring ones already collected.

        Idempotency across restarts comes from the (source, external_id)
        primary key plus INSERT OR IGNORE -- re-running an identical collection
        inserts nothing and is not an error.
        """
        if not docs:
            return 0
        now = datetime.now(timezone.utc).isoformat()
        rows = [
            (
                d.source, d.external_id, d.body, d.permalink,
                d.created_utc.isoformat() if d.created_utc else None,
                d.author_hash, json.dumps(d.payload), now,
            )
            for d in docs
        ]
        before = self.conn.total_changes
        self.conn.executemany(
            "INSERT OR IGNORE INTO raw_document "
            "(source, external_id, body, permalink, created_utc, author_hash, "
            " payload_json, collected_at) VALUES (?,?,?,?,?,?,?,?)",
            rows,
        )
        self.conn.commit()
        return self.conn.total_changes - before

    def start_run(self, source: str, query: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO collection_run (started_at, source, query) VALUES (?,?,?)",
            (datetime.now(timezone.utc).isoformat(), source, query),
        )
        self.conn.commit()
        return cur.lastrowid

    def finish_run(self, run_id: int, fetched: int, inserted: int, error: str | None = None) -> None:
        self.conn.execute(
            "UPDATE collection_run SET finished_at=?, fetched=?, inserted=?, error=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), fetched, inserted, error, run_id),
        )
        self.conn.commit()

    def daily_volume(self) -> list[tuple[str, str, int]]:
        """(date, source, count) -- satisfies 'collected volume queryable per day'."""
        return self.conn.execute(
            "SELECT substr(collected_at,1,10) AS day, source, COUNT(*) "
            "FROM raw_document GROUP BY day, source ORDER BY day DESC, source"
        ).fetchall()


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------

class Collector:
    def __init__(self, sources: list[Source], store: LandingStore):
        self.sources = sources
        self.store = store

    def run(self, queries: list[str], limit: int = 100) -> dict[str, int]:
        """Run every available source over every query.

        An unavailable source is skipped with a log line, not an error: the
        whole point of D11 is that the collector works with whatever it has.
        """
        totals: dict[str, int] = {}
        for source in self.sources:
            ok, reason = source.available()
            if not ok:
                log.info("skipping %s: %s", source.name, reason)
                continue
            for query in queries:
                run_id = self.store.start_run(source.name, query)
                try:
                    docs = source.collect(query, limit)
                    inserted = self.store.insert(docs)
                    self.store.finish_run(run_id, len(docs), inserted)
                    totals[source.name] = totals.get(source.name, 0) + inserted
                    log.info("%s '%s': %d fetched, %d new", source.name, query, len(docs), inserted)
                except NotImplementedError as exc:
                    self.store.finish_run(run_id, 0, 0, f"not implemented: {exc}")
                    log.warning("%s: adapter not implemented yet", source.name)
                    break
                except Exception as exc:  # noqa: BLE001 - one bad source must not kill the run
                    self.store.finish_run(run_id, 0, 0, repr(exc))
                    log.exception("%s '%s' failed", source.name, query)
                time.sleep(1)  # floor politeness delay; adapters add their own
        return totals


# Seeded from the section 3 anchors plus generic discussion terms. Extend as the
# catalogue grows -- W1-3 handles resolving mentions, this only has to cast wide.
DEFAULT_QUERIES = [
    "climbing shoe review",
    "La Sportiva Solution review",
    "Scarpa Drago review",
    "La Sportiva TC Pro review",
    "Scarpa Instinct VSR review",
    "Evolv Defy review",
    "best bouldering shoes",
    "best trad climbing shoes",
    "climbing shoe fit wide feet",
    "climbing shoe downsizing",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="CruxUp corpus collector (W1-0b)")
    parser.add_argument("--limit", type=int, default=100, help="max documents per source per query")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--status", action="store_true", help="print daily volume and exit")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
    )

    store = LandingStore(args.db)

    if args.status:
        rows = store.daily_volume()
        if not rows:
            print("no documents collected yet")
            return
        print(f"{'date':<12} {'source':<10} {'count':>7}")
        for day, source, count in rows:
            print(f"{day:<12} {source:<10} {count:>7}")
        return

    sources: list[Source] = [YouTubeSource(), ForumSource(), RedditSource()]
    for s in sources:
        ok, reason = s.available()
        log.info("source %-8s %s (%s)", s.name, "AVAILABLE" if ok else "unavailable", reason)

    totals = Collector(sources, store).run(DEFAULT_QUERIES, limit=args.limit)
    log.info("run complete: %s", totals or "nothing collected")


if __name__ == "__main__":
    main()
