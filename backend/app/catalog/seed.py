"""[W5-1] Load the seed catalogue from data/shoes.yaml into `shoe`/`shoe_alias`.

Usage
-----
    export DATABASE_URL=postgresql://localhost/cruxup
    python3 backend/app/catalog/seed.py            # seed
    python3 backend/app/catalog/seed.py --dry-run  # validate + exercise, no writes

Design notes
------------
*Validation is a precondition, not a courtesy.* The catalogue is hand-written
and has already carried three annotation errors. seed() refuses to run against
an invalid catalogue rather than loading a broken one and discovering it later
in the quadrant UI.

*Idempotent by identity.* Upserts on (brand, model, version, gender) -- the
same key as `shoe_unique_identity`. Re-seeding an unchanged catalogue is a
no-op; re-seeding a corrected one updates in place and keeps the shoe's UUID,
which matters because `recommendation.shoe_id` and (later) `mention.shoe_id`
point at it. Delete-and-reinsert would orphan that history.

*Aliases are replaced, not merged.* Removing an alias from the YAML must remove
it from the database, otherwise a stale alias keeps matching mentions forever.

The YAML carries two keys that are NOT columns: `anchor` (validation metadata)
and `note` (documentation). They are deliberately dropped here -- see COLUMNS.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate import CATALOG, validate  # noqa: E402

# Only these YAML keys map to `shoe` columns. `anchor` and `note` are
# intentionally absent: the first is validation metadata, the second is prose.
COLUMNS = (
    "brand", "model", "version", "gender", "last_shape", "downturn",
    "stiffness_spec", "closure", "rubber", "msrp_usd",
    "quadrant_x_prior", "quadrant_y_prior",
)

IDENTITY = ("brand", "model", "version", "gender")


@dataclass
class SeedResult:
    inserted: int = 0
    updated: int = 0
    aliases: int = 0
    without_msrp: int = 0

    def __str__(self) -> str:
        return (
            f"{self.inserted} inserted, {self.updated} updated, "
            f"{self.aliases} aliases, {self.without_msrp} without msrp"
        )


def load_catalog(path: Path = CATALOG) -> list[dict]:
    """Read and validate the catalogue. Raises ValueError if it is unsound."""
    errors = validate(path)
    if errors:
        raise ValueError(
            "catalogue failed validation; refusing to seed:\n  - "
            + "\n  - ".join(errors)
        )
    return (yaml.safe_load(path.read_text()) or {})["shoes"]


def _row(shoe: dict) -> dict:
    """Project a YAML entry onto the `shoe` columns, normalising defaults."""
    row = {c: shoe.get(c) for c in COLUMNS}
    # `version` participates in the unique key, so it is '' and never NULL --
    # in SQL, NULL != NULL, so a NULL version would make every versionless
    # shoe distinct from every other and defeat the upsert entirely.
    row["version"] = row["version"] or ""
    row["gender"] = row["gender"] or "unisex"
    return row


def seed(conn, shoes: list[dict], dry_run: bool = False) -> SeedResult:
    result = SeedResult()
    placeholders = ", ".join(f"%({c})s" for c in COLUMNS)
    collist = ", ".join(COLUMNS)
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in COLUMNS if c not in IDENTITY)

    with conn.cursor() as cur:
        for shoe in shoes:
            row = _row(shoe)
            if row["msrp_usd"] is None:
                result.without_msrp += 1

            # xmax = 0 distinguishes a fresh INSERT from a DO UPDATE.
            cur.execute(
                f"INSERT INTO shoe ({collist}) VALUES ({placeholders}) "
                f"ON CONFLICT (brand, model, version, gender) "
                f"DO UPDATE SET {updates} "
                f"RETURNING id, (xmax = 0) AS was_insert",
                row,
            )
            shoe_id, was_insert = cur.fetchone()
            if was_insert:
                result.inserted += 1
            else:
                result.updated += 1

            # Replace rather than merge: a removed alias must stop matching.
            cur.execute("DELETE FROM shoe_alias WHERE shoe_id = %s", (shoe_id,))
            for alias in shoe.get("aliases") or []:
                cur.execute(
                    "INSERT INTO shoe_alias (shoe_id, alias) VALUES (%s, %s)",
                    (shoe_id, alias),
                )
                result.aliases += 1

        if dry_run:
            conn.rollback()
        else:
            conn.commit()

    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Seed the shoe catalogue (W5-1)")
    ap.add_argument("--catalog", type=Path, default=CATALOG)
    ap.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    ap.add_argument("--dry-run", action="store_true",
                    help="validate and exercise the load, then roll back")
    args = ap.parse_args()

    if not args.database_url:
        print("error: set DATABASE_URL or pass --database-url", file=sys.stderr)
        return 2

    try:
        shoes = load_catalog(args.catalog)
    except ValueError as exc:
        print(f"\n{exc}", file=sys.stderr)
        return 1

    import psycopg

    try:
        with psycopg.connect(args.database_url) as conn:
            result = seed(conn, shoes, dry_run=args.dry_run)
    except psycopg.errors.UndefinedTable:
        print(
            "error: the `shoe` table does not exist. Apply the migration first:\n"
            "  psql -d <db> -f backend/app/db/migrations/0001_init.sql",
            file=sys.stderr,
        )
        return 1
    except psycopg.OperationalError as exc:
        print(f"error: cannot connect to the database: {exc}", file=sys.stderr)
        return 1

    print(f"\n{'[dry run, rolled back] ' if args.dry_run else ''}{result}")
    if result.without_msrp:
        print(
            f"note: {result.without_msrp} shoes have no msrp_usd. The budget "
            f"gate (section 7.6) must not treat those as within budget."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
