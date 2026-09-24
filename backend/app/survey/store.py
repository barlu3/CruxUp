"""[W4'-1] Persist one survey submission to `user_survey` (0001_init.sql).

Usage
-----
    export DATABASE_URL=postgresql://localhost/cruxup
    python3 backend/app/survey/store.py submission.json            # insert
    python3 backend/app/survey/store.py submission.json --dry-run  # validate + resolve + exercise the insert, no write

Design notes
------------
*Two validation stages, one error list.* schema.validate() checks scalar
fields and top-level shape without touching the catalog; anchors.resolve_
anchors() resolves known_good_shoes / known_bad_shoes, which needs the
catalog. build_survey_row() runs both and merges their errors before any
database call, so a caller sees every problem in one round trip -- the same
"validation is a precondition, not a courtesy" stance as catalog/seed.py's
load_catalog().

*The only identity is survey_token.* 0001_init.sql has no other unique,
non-null handle on `user_survey`. Tokens are generated with
`secrets.token_urlsafe` -- a CSPRNG -- never `random`, a uuid4 used as a
secret, or a timestamp, any of which would make a token guessable.

*Unknown top-level keys are refused before this module is reached*
(schema.ALLOWED_KEYS), and `shoe_id` is refused inside every anchor entry
(anchors.ANCHOR_ALLOWED_KEYS) -- both are D4's "derived values only, no
direct identifiers" enforced as allow-lists, not deny-lists.

*Parameterised, one transaction, `--dry-run` rolls back* -- the same
contract as catalog/seed.py's seed(). `_insert_row` is split out from
`insert_survey` only so a caller (namely the DB-backed round-trip test) can
read back the row inside the same, still-open transaction before it is ever
committed.

`DATABASE_URL` is resolved at USE time via config.load_dotenv(), inside
main() -- not at import time -- for the same reason collector.py reads its
salt at hash time, not import time: an import that ran before .env was
loaded would silently see nothing.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import anchors  # noqa: E402
import schema  # noqa: E402

# secrets.token_urlsafe(32) draws 32 random bytes from the OS CSPRNG and
# base64url-encodes them (~43 characters, no padding). 32 bytes is the same
# order of entropy as a UUID4 used correctly, comfortably infeasible to guess
# or enumerate.
TOKEN_BYTES = 32

# Column order for the INSERT. Excludes id, created_at (DB defaults) and
# survey_token, which is prepended separately -- it is generated here, never
# accepted from a submission.
INSERT_COLUMNS = ("survey_token",) + schema.SCALAR_FIELDS + schema.ANCHOR_FIELDS


def new_survey_token() -> str:
    """A fresh, unguessable survey_token. CSPRNG per the task's requirement --
    never random/uuid4-as-secret/timestamp."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def build_survey_row(
    payload: object, catalog: anchors.CatalogLookup
) -> tuple[dict | None, list[str]]:
    """Validate + resolve one submission. Returns (row, errors).

    `row` is a complete, ready-to-insert dict (including a fresh
    survey_token) when `errors` is empty; otherwise `row` is None and
    `errors` names every problem found across both validation stages.
    """
    errors = schema.validate(payload)

    good_raw = payload.get("known_good_shoes", []) if isinstance(payload, dict) else []
    bad_raw = payload.get("known_bad_shoes", []) if isinstance(payload, dict) else []
    # Only attempt resolution once the shape checks above confirm these are
    # actually lists -- resolve_anchors() would otherwise report the same
    # "must be a list" problem a second time in different words.
    # The count cap is re-checked here, not just in schema.validate(), because
    # resolution below issues at least one catalog round trip PER anchor: an
    # oversized list must never reach it, even though validate() has already
    # recorded the error and this call is doomed to return it.
    over_cap = (
        isinstance(good_raw, list) and isinstance(bad_raw, list)
        and len(good_raw) + len(bad_raw) > schema.MAX_ANCHORS_TOTAL
    )

    if isinstance(good_raw, list) and isinstance(bad_raw, list) and not over_cap:
        resolved_good, resolved_bad, anchor_errors = anchors.resolve_anchors(
            good_raw, bad_raw, catalog
        )
        errors.extend(anchor_errors)
    else:
        resolved_good, resolved_bad = [], []

    if errors:
        return None, errors

    row = {field: payload.get(field) for field in schema.SCALAR_FIELDS}
    row["known_good_shoes"] = resolved_good
    row["known_bad_shoes"] = resolved_bad
    row["survey_token"] = new_survey_token()
    return row, []


def _insert_row(cur, row: dict) -> None:
    """The bare parameterised INSERT, with no commit/rollback -- see
    `insert_survey`. Split out so a test can read the row back inside the
    same still-open transaction before anything is committed.
    """
    from psycopg.types.json import Jsonb

    params = dict(row)
    params["known_good_shoes"] = Jsonb(row["known_good_shoes"])
    params["known_bad_shoes"] = Jsonb(row["known_bad_shoes"])

    collist = ", ".join(INSERT_COLUMNS)
    placeholders = ", ".join(f"%({c})s" for c in INSERT_COLUMNS)
    # %(name)s named-parameter binding throughout -- never f-string
    # interpolation of a value into the SQL text (the house rule; see
    # catalog/seed.py).
    cur.execute(f"INSERT INTO user_survey ({collist}) VALUES ({placeholders})", params)


def insert_survey(conn, row: dict, dry_run: bool = False) -> str:
    """Insert one `user_survey` row in a single transaction. Returns its
    survey_token. `dry_run=True` rolls back instead of committing, so the
    whole path (including JSONB adaptation) is exercised with no write."""
    with conn.cursor() as cur:
        _insert_row(cur, row)
        if dry_run:
            conn.rollback()
        else:
            conn.commit()
    return row["survey_token"]


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate, resolve and persist a survey submission (W4'-1)")
    ap.add_argument("payload", type=Path, help="path to a JSON survey submission")
    ap.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    ap.add_argument(
        "--dry-run", action="store_true",
        help="validate, resolve against the catalog and exercise the insert, then roll back",
    )
    args = ap.parse_args()

    try:
        payload = json.loads(args.payload.read_bytes())
    # read_bytes(), not read_text(): see schema.main() -- the locale encoding
    # would turn a legitimate "42 ½" size into mojibake. ValueError covers both
    # json.JSONDecodeError and UnicodeDecodeError (invalid bytes).
    # RecursionError: json.loads blows the stack on deeply nested input and
    # is not a JSONDecodeError, so without it a crafted payload exits with a
    # traceback rather than a clean error.
    except (OSError, ValueError, RecursionError) as exc:
        print(f"error: cannot read payload: {exc}", file=sys.stderr)
        return 1

    # Validation is a precondition, not a courtesy (catalog/seed.py's stance,
    # via load_catalog() before any connection): the scalar-field/shape half
    # of validation needs no catalog, so it runs -- and can already reject --
    # before DATABASE_URL is even resolved. Anchor resolution still needs a
    # live catalog and is re-checked by build_survey_row() once connected.
    schema_errors = schema.validate(payload)
    if schema_errors:
        print(f"\n{len(schema_errors)} ERROR(S):", file=sys.stderr)
        for e in schema_errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    # DATABASE_URL usually lives in .env, which Python does not read natively.
    if not args.database_url:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        try:
            from config import load_dotenv

            load_dotenv()
            args.database_url = os.environ.get("DATABASE_URL")
        except ImportError:
            pass

    if not args.database_url:
        print("error: set DATABASE_URL or pass --database-url", file=sys.stderr)
        return 2

    import psycopg

    try:
        with psycopg.connect(args.database_url) as conn:
            catalog = anchors.PostgresCatalog(conn)
            row, errors = build_survey_row(payload, catalog)
            if errors:
                print(f"\n{len(errors)} ERROR(S):", file=sys.stderr)
                for e in errors:
                    print(f"  - {e}", file=sys.stderr)
                return 1
            token = insert_survey(conn, row, dry_run=args.dry_run)
    # Order matters: UniqueViolation and UndefinedTable are both subclasses of
    # psycopg.Error, so the specific handlers must precede the catch-all.
    except psycopg.errors.UndefinedTable:
        print(
            "error: the `user_survey` table does not exist. Apply the migration first:\n"
            "  psql -d <db> -f backend/app/db/migrations/0001_init.sql",
            file=sys.stderr,
        )
        return 1
    except psycopg.errors.UniqueViolation:
        # survey_token is NOT NULL UNIQUE. With 32 CSPRNG bytes a collision is
        # ~2^-256, so this effectively means the token column was written by
        # something other than new_survey_token(). Report it rather than
        # exiting on a raw traceback.
        print(
            "error: survey_token collision -- retry. If this recurs, tokens are "
            "not being generated by new_survey_token().",
            file=sys.stderr,
        )
        return 1
    except psycopg.OperationalError as exc:
        print(f"error: cannot connect to the database: {exc}", file=sys.stderr)
        return 1
    except psycopg.Error as exc:
        # Catch-all so a malformed value that survives validation (and so is a
        # validation bug worth seeing) fails with a readable message instead
        # of a traceback exposing internal paths. The connection context
        # manager has already rolled back by the time this runs, so nothing is
        # half-written.
        print(f"error: database rejected the submission: {exc}", file=sys.stderr)
        return 1

    print(f"{'[dry run, rolled back] ' if args.dry_run else ''}survey_token={token}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
