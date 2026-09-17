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
Writes to a local landing table, NOT to the section 8.2 `mention` schema. Raw
payloads land here verbatim; W1-full normalises them later.

RETENTION IS SOURCE-DEPENDENT. The original design kept raw data indefinitely.
That does not hold for YouTube: its Developer Policies (III.E.4.d) cap stored
Non-Authorized Data at 30 days, and III.E.4.h / III.E.2.a appear to prohibit
the aggregation and derived metrics section 7.4 relies on. YouTube collection
is not cleared -- see timeline.md section 10.2 -- and each source's terms must
set its retention before that source collects anything.

PII
---
Author identifiers are hashed at write time and the raw value is never stored.
See `_hash_author`.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import logging
import os
import sqlite3
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

log = logging.getLogger("collector")

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "corpus_landing.sqlite3"

# Author pseudonymisation key.
#
# Read when a hash is computed, NOT at import: main() loads .env after this
# module is imported, so an import-time read silently ignored a salt defined
# only in .env and fell back to a public default -- every stored hash was then
# reproducible by anyone who read this file.
#
# This IS a secret. YouTube channel IDs are public, so whoever holds the key can
# hash candidate IDs and match them against stored hashes. There is no default;
# collection refuses to start without a real key.
SALT_ENV = "CRUXUP_AUTHOR_SALT"
MIN_SALT_LENGTH = 32
_BURNED_SALTS = {"cruxup-dev-salt"}  # the former public fallback; never valid


class MissingAuthorSalt(RuntimeError):
    """CRUXUP_AUTHOR_SALT is absent, burned, or too short to protect stored hashes."""


def _author_salt() -> bytes:
    salt = os.environ.get(SALT_ENV, "")
    if not salt or salt in _BURNED_SALTS or len(salt) < MIN_SALT_LENGTH:
        raise MissingAuthorSalt(
            f"{SALT_ENV} must be a random value of at least {MIN_SALT_LENGTH} "
            f"characters. Generate one with: "
            f'python3 -c "import secrets; print(secrets.token_hex(32))"'
        )
    return salt.encode()


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
    """Pseudonymise an author identifier. The raw value never reaches storage.

    HMAC-SHA256 keyed with the deployment secret -- the standard primitive for
    a keyed pseudonym. Every hash made under the old import-time salt was
    already invalid, so this was the one point where switching constructions
    cost nothing. Raises MissingAuthorSalt rather than hash with a guessable key.
    """
    if not author:
        return None
    return hmac.new(_author_salt(), author.encode(), hashlib.sha256).hexdigest()


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


QUOTA_SCHEMA = """
CREATE TABLE IF NOT EXISTS api_quota (
    day    TEXT    NOT NULL,   -- quota day, America/Los_Angeles
    bucket TEXT    NOT NULL,
    used   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, bucket)
);
"""


class QuotaLedger:
    """Persistent, date-keyed quota counters, reserved BEFORE each request.

    Persistent because an in-memory counter restarts at zero in every process,
    so separate runs on one day could together exceed the provider's quota.
    Reserved first because Google charges quota for every request "even if
    invalid": counting only after success under-counts precisely the failing
    requests that tend to repeat.

    Days are keyed in America/Los_Angeles because YouTube quotas reset at
    midnight Pacific time.
    """

    def __init__(self, conn: sqlite3.Connection, clock=None):
        self.conn = conn
        self.conn.executescript(QUOTA_SCHEMA)
        self.conn.commit()
        self._clock = clock or (lambda: datetime.now(ZoneInfo("America/Los_Angeles")))

    def day(self) -> str:
        return self._clock().date().isoformat()

    def reserve(self, bucket: str, cost: int, limit: int) -> None:
        """Atomically reserve `cost` units in `bucket`, or raise QuotaExceeded."""
        day = self.day()
        with self.conn:  # one transaction: create the row if absent, then a guarded increment
            self.conn.execute(
                "INSERT OR IGNORE INTO api_quota (day, bucket, used) VALUES (?, ?, 0)",
                (day, bucket),
            )
            cur = self.conn.execute(
                "UPDATE api_quota SET used = used + ? "
                "WHERE day = ? AND bucket = ? AND used + ? <= ?",
                (cost, day, bucket, cost, limit),
            )
        if cur.rowcount == 0:
            raise QuotaExceeded(f"{bucket} quota exhausted for {day} (limit {limit})")

    def used(self, bucket: str, day: str | None = None) -> int:
        row = self.conn.execute(
            "SELECT used FROM api_quota WHERE day = ? AND bucket = ?",
            (day or self.day(), bucket),
        ).fetchone()
        return row[0] if row else 0

    @classmethod
    def in_memory(cls, clock=None) -> "QuotaLedger":
        """Non-persistent ledger for tests and library use. main() never uses it."""
        return cls(sqlite3.connect(":memory:"), clock=clock)


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
    Per Google's quota documentation (checked 2026-09-16), search.list has its
    OWN bucket -- 100 calls/day at 1 per call -- separate from the 10,000-unit
    pool shared by every other endpoint, including commentThreads.list (1 per
    call). The previous code charged each search 100 units against the shared
    pool, which misstated the search limit and starved comment collection.

    Both buckets are persisted in a date-keyed QuotaLedger and reserved before
    each request, so failed requests count and separate runs on the same day
    cannot jointly overrun the provider's quota.

    Transport is injected so the adapter is testable without network access.
    """

    name = "youtube"

    API = "https://www.googleapis.com/youtube/v3"
    SEARCH_BUCKET = "youtube.search"
    SEARCH_COST = 1
    SEARCH_DAILY_LIMIT = 100
    UNITS_BUCKET = "youtube.units"
    UNITS_DAILY_LIMIT = 10_000
    COST_COMMENT_THREADS = 1

    def __init__(
        self,
        api_key: str | None = None,
        fetch=None,
        quota: QuotaLedger | None = None,
        search_limit: int = SEARCH_DAILY_LIMIT,
        unit_limit: int = UNITS_DAILY_LIMIT,
        videos_per_query: int = 5,
    ):
        self.api_key = api_key or os.environ.get("YOUTUBE_API_KEY")
        self._fetch = fetch or self._http_get
        # main() injects a persistent ledger. The in-memory fallback exists for
        # tests and library use and does NOT protect the provider's daily quota.
        self.quota = quota or QuotaLedger.in_memory()
        self.search_limit = search_limit
        self.unit_limit = unit_limit
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

    def _call(self, endpoint: str, bucket: str, cost: int, limit: int, **params) -> dict:
        # Reserve BEFORE the request: Google charges quota even for requests
        # that fail, so the ledger must too.
        self.quota.reserve(bucket, cost, limit)
        params["key"] = self.api_key
        return self._fetch(f"{self.API}/{endpoint}", params)

    # -- collection --------------------------------------------------------

    def _search_videos(self, query: str) -> list[tuple[str, str]]:
        """(video_id, title) for videos matching `query`."""
        data = self._call(
            "search",
            self.SEARCH_BUCKET,
            self.SEARCH_COST,
            self.search_limit,
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
                data = self._call(
                    "commentThreads",
                    self.UNITS_BUCKET,
                    self.COST_COMMENT_THREADS,
                    self.unit_limit,
                    **params,
                )
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

    # Load .env before any source reads os.environ. Without this a key sitting
    # in .env looks identical to no key at all -- every source reports
    # "unavailable" and the run silently collects nothing.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    try:
        from config import load_dotenv

        keys = load_dotenv()
        if keys:
            log.info("loaded %d key(s) from .env: %s", len(keys), ", ".join(sorted(keys)))
    except ImportError:
        log.debug("config.load_dotenv unavailable; using the ambient environment")

    store = LandingStore(args.db)
    ledger = QuotaLedger(store.conn)

    if args.status:
        rows = store.daily_volume()
        if not rows:
            print("no documents collected yet")
        else:
            print(f"{'date':<12} {'source':<10} {'count':>7}")
            for day, source, count in rows:
                print(f"{day:<12} {source:<10} {count:>7}")
        print(
            f"\nYouTube quota for {ledger.day()} (Pacific): "
            f"search {ledger.used(YouTubeSource.SEARCH_BUCKET)}/{YouTubeSource.SEARCH_DAILY_LIMIT} calls, "
            f"units {ledger.used(YouTubeSource.UNITS_BUCKET)}/{YouTubeSource.UNITS_DAILY_LIMIT}"
        )
        return

    # Fail before any request is made, not on the first comment hashed.
    try:
        _author_salt()
    except MissingAuthorSalt as exc:
        log.error("refusing to collect: %s", exc)
        raise SystemExit(2)

    sources: list[Source] = [YouTubeSource(quota=ledger), ForumSource(), RedditSource()]
    for s in sources:
        ok, reason = s.available()
        log.info("source %-8s %s (%s)", s.name, "AVAILABLE" if ok else "unavailable", reason)

    totals = Collector(sources, store).run(DEFAULT_QUERIES, limit=args.limit)
    log.info("run complete: %s", totals or "nothing collected")


if __name__ == "__main__":
    main()
