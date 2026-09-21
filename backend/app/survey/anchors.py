"""[W4'-1] Anchor resolution: known_good_shoes (G) / known_bad_shoes (B) against
the shoe catalog (section 7.1).

Anchors are the highest-signal fit input (timeline.md section 7.1): shoes the
user already knows fit well (G) or poorly (B). Each entry names a shoe by
(brand, model[, version][, gender]); this module turns that name into the
catalog's `shoe.id` or refuses with a specific error -- it never guesses.

Why ambiguity is a hard error, not a heuristic
-----------------------------------------------
`shoe_unique_identity` in 0001_init.sql is (brand, model, version, gender), not
(brand, model). Several real catalog rows share (brand, model) and differ only
by `version`:

    Scarpa Instinct        -> VS, VSR
    La Sportiva Katana     -> Lace, Velcro
    La Sportiva Solution   -> '' (base), Comp

Instinct VSR and the base Solution are both section 3 calibration anchors. A
silent pick between two rows sharing a name -- e.g. defaulting to "the first
match" -- would silently corrupt calibration-grade input. So resolution here
is deliberately conservative: unambiguous only, or an error naming every
candidate, never a guess.

Disambiguation paths, in order of preference:
  1. An explicit `version` and/or `gender` on the anchor narrows the identity
     match directly (timeline.md section 7.1 acceptance criteria).
  2. `shoe_alias_globally_unique` (0001_init.sql) indexes on lower(alias) and
     is unique across the WHOLE catalog, so a `model` value that happens to
     BE a registered alias (e.g. "Solution Comp", "Katana Lace", "VSR") is an
     unambiguous match by construction. Tried ONLY when the direct (brand,
     model) identity match is completely absent (0 rows) -- deliberately NOT
     tried as a tie-break when identity is already ambiguous (>1 rows), so
     that e.g. bare "Solution" (which happens to also be a registered alias
     of the base shoe) is treated exactly like bare "Instinct" and "Katana":
     ambiguous, and rejected, not resolved by catalog trivia the caller has
     no way to know about. "Solution Comp" and "VSR" work as disambiguators
     precisely BECAUSE they do not collide with any raw shoe.model value.

`size` is an OPTIONAL, opaque brand-size string (D9 / DDL comment on
known_good_shoes). This module never reads `shoe_size_map` -- it is currently
empty (0 rows), and D9 makes `size_exists` the only hard sizing gate, decided
downstream in the scorer, not here.

Dependency injection
---------------------
`CatalogLookup` is a Protocol so the default test suite can resolve anchors
against a fake, in-process catalog (`StaticCatalog`) with no network and no
database -- the same shape as `QuotaLedger.in_memory()` in
scraping/collector.py. `PostgresCatalog` is the real implementation, used by
store.py and by the optional DB-backed tests.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

# Mirrors shoe_gender_valid in 0001_init.sql. Reused here only to validate an
# anchor's OPTIONAL `gender` disambiguator against the same vocabulary the
# catalog itself enforces.
GENDERS = {"mens", "womens", "unisex"}

# The only sub-keys an anchor entry may carry. `shoe_id` is deliberately
# absent: it is the OUTPUT of resolution, never an accepted input -- letting a
# caller supply it directly would let them point an anchor at an arbitrary
# shoe without it ever having matched brand/model, which defeats the point of
# resolving at all.
ANCHOR_ALLOWED_KEYS = frozenset({"brand", "model", "version", "gender", "size"})

# `size` is the one anchor field the catalog never constrains: brand, model
# and version must match a real catalog row or the anchor does not resolve at
# all, but `size` is opaque free text that is stored verbatim (D9 -- see the
# module docstring). An allow-list on KEY NAMES does nothing to bound VALUE
# content, so without a cap here an email address, or a multi-megabyte blob,
# rides an allowed key straight into user_survey -- contradicting that table's
# own D4 guarantee in 0001_init.sql ("derived measurements only... no direct
# identifiers"). 64 characters is generous for any real brand size:
# "US M 9.5 / EU 42.5" is 18.
ANCHOR_SIZE_MAX_LEN = 64

# brand/model/version are bound into a catalog query BEFORE it is known
# whether they match anything, so they are capped before reaching the
# database rather than after. The longest real catalog brand+model is far
# under this.
ANCHOR_NAME_MAX_LEN = 128

# A LENGTH cap alone does not deliver D4's "no direct identifiers": an email
# address is ~30 characters and fits any sane cap. Constraining the CHARACTER
# SET is what actually closes that gap -- "a.person@example.com" is rejected
# on '@', while every real sizing convention passes:
#   42.5 | US M 9.5 / EU 42.5 | UK 8.5 | EU 43 2/3 | 42 1/2 | 9.5+
# Mirrors this module's allow-list stance (ANCHOR_ALLOWED_KEYS): enumerate
# what is permitted rather than guess at what to forbid.
SIZE_ALLOWED_CHARS = frozenset(
    "0123456789"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz"
    " ./+-\u00bd\u2153\u2154\u00bc\u00be"
)


def _text_error(value: str, where: str, field: str, max_len: int) -> str | None:
    """Reject free text that must never reach a query parameter or storage.

    Three failure modes, none of which the isinstance checks above catch, and
    all of which otherwise surface as a crash rather than a validation error:

      * over-long input -- see ANCHOR_SIZE_MAX_LEN / ANCHOR_NAME_MAX_LEN;
      * a NUL byte, which Postgres cannot store in text or jsonb and which
        arrives as an untranslatable-character DataError from inside psycopg;
      * a lone UTF-16 surrogate, which is representable in a Python str (it
        survives json.loads) but has no UTF-8 encoding, so psycopg raises a
        bare UnicodeEncodeError while encoding the parameter for the wire.

    Catching all three here keeps this module failing closed *by design*,
    with a named error a caller can act on, rather than by crashing.
    """
    if len(value) > max_len:
        return f"{where}: {field!r} is {len(value)} characters, maximum {max_len}"
    if "\x00" in value:
        return f"{where}: {field!r} must not contain a NUL byte"
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return f"{where}: {field!r} contains an unencodable character (lone surrogate)"
    return None


def _size_charset_error(value: str, where: str) -> str | None:
    """Reject a `size` holding characters no sizing convention uses.

    Runs AFTER _text_error, so length / NUL / surrogate keep their own
    specific messages and this reports only genuine charset violations.
    """
    bad = sorted({c for c in value if c not in SIZE_ALLOWED_CHARS})
    if bad:
        return (
            f"{where}: 'size' contains {bad} -- it records a brand size, not "
            f"free text (D4: no direct identifiers)"
        )
    return None


def _key(s: str) -> str:
    """Case-insensitive comparison key. Mirrors shoe_alias_globally_unique's
    `lower(alias)` index and the task's 'resolve case-insensitively'."""
    return s.strip().lower()


@dataclass(frozen=True)
class CatalogShoe:
    """Minimal projection of `shoe` needed to resolve an anchor -- exactly the
    columns in shoe_unique_identity (brand, model, version, gender) plus the id."""

    shoe_id: str
    brand: str
    model: str
    version: str  # '' not NULL, matching the DDL comment on shoe.version
    gender: str

    def describe(self) -> str:
        version = self.version or "''"
        return f"{self.brand} {self.model} (version={version}, gender={self.gender})"


class CatalogLookup(Protocol):
    """Dependency-injected catalog access. Implementations: StaticCatalog (tests,
    dependency injection) and PostgresCatalog (real, used by store.py)."""

    def by_identity(self, brand: str, model: str) -> list[CatalogShoe]:
        """Case-insensitive (brand, model) candidates. Version/gender are
        filtered by the caller -- this returns every version/gender under the
        name so ambiguity is visible."""
        ...

    def by_alias(self, alias: str) -> CatalogShoe | None:
        """Case-insensitive shoe_alias lookup. Globally unique, so at most one
        shoe can ever come back."""
        ...


class StaticCatalog:
    """In-memory CatalogLookup for tests and library use -- never used by
    main() / store.py against a real submission. Named `StaticCatalog` rather
    than `.in_memory()` because a catalog is data supplied up front, not a
    stateful store opened empty (contrast QuotaLedger.in_memory())."""

    def __init__(
        self,
        shoes: Iterable[CatalogShoe] = (),
        aliases: dict[str, str] | None = None,
    ) -> None:
        """`aliases` maps alias text -> shoe_id (any case; normalised here)."""
        self._shoes = list(shoes)
        self._by_id = {s.shoe_id: s for s in self._shoes}
        self._aliases = {_key(k): v for k, v in (aliases or {}).items()}

    def by_identity(self, brand: str, model: str) -> list[CatalogShoe]:
        b, m = _key(brand), _key(model)
        return [s for s in self._shoes if _key(s.brand) == b and _key(s.model) == m]

    def by_alias(self, alias: str) -> CatalogShoe | None:
        shoe_id = self._aliases.get(_key(alias))
        return self._by_id.get(shoe_id) if shoe_id is not None else None


class PostgresCatalog:
    """Real CatalogLookup over `shoe` / `shoe_alias`. Takes an already-open
    psycopg connection (never opens its own), so it never imports `psycopg`
    itself -- store.py owns the connection lifecycle, exactly like
    catalog/seed.py's `seed(conn, ...)`. Only reached by store.py and by
    DB-backed tests; the default hermetic suite never constructs this."""

    def __init__(self, conn):
        self._conn = conn

    def by_identity(self, brand: str, model: str) -> list[CatalogShoe]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT id, brand, model, version, gender FROM shoe "
                "WHERE lower(brand) = lower(%s) AND lower(model) = lower(%s)",
                (brand, model),
            )
            return [
                CatalogShoe(str(row[0]), row[1], row[2], row[3], row[4])
                for row in cur.fetchall()
            ]

    def by_alias(self, alias: str) -> CatalogShoe | None:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT s.id, s.brand, s.model, s.version, s.gender "
                "FROM shoe_alias sa JOIN shoe s ON s.id = sa.shoe_id "
                "WHERE lower(sa.alias) = lower(%s)",
                (alias,),
            )
            row = cur.fetchone()
            return CatalogShoe(str(row[0]), row[1], row[2], row[3], row[4]) if row else None


def _resolve_one(
    entry: object, list_name: str, index: int, catalog: CatalogLookup
) -> tuple[dict | None, str | None]:
    """Resolve one anchor dict. Returns (resolved_dict, None) or (None, error).

    `resolved_dict` is a shallow copy of `entry` with `shoe_id` added -- the
    caller's other keys (e.g. `size`) pass through untouched, so `brand`,
    `model`, `gender` and `size` are stored with the caller's ORIGINAL casing.
    Only `shoe_id` is canonical; nothing downstream should assume the other
    sub-fields are normalised.

    Error contract, deliberately NARROWER than schema.validate()'s: this
    returns the FIRST problem with this entry, not every problem with it.
    resolve_anchors() still attempts every entry, so a caller sees one error
    per bad anchor in a single round trip -- but an entry that is wrong in two
    ways reports only the first. Resolution is sequential (each check's
    validity depends on the ones before it, and the catalog lookup depends on
    all of them), so accumulating within an entry would mean reporting errors
    derived from values already known to be bad.
    """
    where = f"{list_name}[{index}]"

    if not isinstance(entry, dict):
        return None, f"{where}: must be a mapping, got {type(entry).__name__}"

    if "shoe_id" in entry:
        return None, (
            f"{where}: 'shoe_id' is resolved from the catalog and must not be "
            f"supplied by the caller"
        )
    extra = set(entry) - ANCHOR_ALLOWED_KEYS
    if extra:
        return None, f"{where}: unknown key(s) {sorted(extra)}"

    brand = entry.get("brand")
    model = entry.get("model")
    if not isinstance(brand, str) or not brand.strip():
        return None, f"{where}: 'brand' is required and must be a non-empty string"
    if not isinstance(model, str) or not model.strip():
        return None, f"{where}: 'model' is required and must be a non-empty string"
    for field, value in (("brand", brand), ("model", model)):
        bad = _text_error(value, where, field, ANCHOR_NAME_MAX_LEN)
        if bad:
            return None, bad

    size = entry.get("size")
    if size is not None and not isinstance(size, str):
        return None, f"{where}: 'size' must be a string if given, got {type(size).__name__}"
    if isinstance(size, str):
        bad = _text_error(size, where, "size", ANCHOR_SIZE_MAX_LEN)
        if bad:
            return None, bad
        bad = _size_charset_error(size, where)
        if bad:
            return None, bad

    version = entry.get("version")
    if "version" in entry and not isinstance(version, str):
        return None, f"{where}: 'version' must be a string if given, got {type(version).__name__}"
    if isinstance(version, str):
        bad = _text_error(version, where, "version", ANCHOR_NAME_MAX_LEN)
        if bad:
            return None, bad

    gender = entry.get("gender")
    if "gender" in entry:
        if not isinstance(gender, str) or _key(gender) not in GENDERS:
            return None, f"{where}: 'gender' must be one of {sorted(GENDERS)}, got {gender!r}"

    # --- identity match: exact (brand, model), narrowed by version/gender if given ---
    candidates = catalog.by_identity(brand, model)
    if "version" in entry:
        candidates = [c for c in candidates if _key(c.version) == _key(version)]
    if "gender" in entry:
        candidates = [c for c in candidates if _key(c.gender) == _key(gender)]

    # --- alias fallback: ONLY when identity matched nothing at all ---
    # Deliberately NOT tried as a tie-break when identity is already ambiguous
    # (>1 candidates): "Solution" is itself a registered alias of the BASE
    # Solution only, so treating alias as a tie-breaker would silently
    # resolve bare "Solution" while leaving bare "Instinct" and "Katana"
    # ambiguous -- an inconsistent rule that depends on catalog trivia the
    # caller cannot see. Restricting the fallback to the 0-candidate case
    # makes all three of the task's named pairs behave identically: a bare,
    # genuinely shared model name is ALWAYS ambiguous, and "Solution Comp" /
    # "Katana Lace" / "VSR" work as disambiguators only because they do NOT
    # collide with a raw shoe.model value (that column holds "Solution" /
    # "Katana" / "Instinct" respectively).
    if len(candidates) == 0:
        alias_hit = catalog.by_alias(model)
        if alias_hit is not None and _key(alias_hit.brand) == _key(brand):
            candidates = [alias_hit]

    if len(candidates) == 0:
        return None, f"{where}: unknown shoe -- no catalog match for '{brand}' '{model}'"

    if len(candidates) > 1:
        options = "; ".join(c.describe() for c in candidates)
        return None, (
            f"{where}: ambiguous '{brand}' '{model}' -- {len(candidates)} candidates: "
            f"{options}. Disambiguate with 'version' and/or 'gender', or use a "
            f"shoe_alias surface form as 'model' (e.g. 'Solution Comp' vs 'Solution')."
        )

    resolved = dict(entry)
    resolved["shoe_id"] = candidates[0].shoe_id
    return resolved, None


def resolve_anchors(
    good: object, bad: object, catalog: CatalogLookup
) -> tuple[list[dict], list[dict], list[str]]:
    """Resolve known_good_shoes (`good`) and known_bad_shoes (`bad`) against
    `catalog`. Returns (resolved_good, resolved_bad, errors).

    Every entry is attempted -- one bad anchor does not stop the others from
    being checked, matching the house `validate() -> list[str]` style
    (catalog/validate.py): a caller sees every problem in one round trip.

    A shoe resolved into BOTH lists is contradictory input (the user cannot
    report the same shoe as both a fit and a miss) and is rejected even
    though each entry resolves individually cleanly.
    """
    errors: list[str] = []

    if not isinstance(good, list):
        errors.append(f"known_good_shoes must be a list, got {type(good).__name__}")
        good = []
    if not isinstance(bad, list):
        errors.append(f"known_bad_shoes must be a list, got {type(bad).__name__}")
        bad = []

    resolved_good: list[dict] = []
    for i, entry in enumerate(good):
        resolved, error = _resolve_one(entry, "known_good_shoes", i, catalog)
        if error is not None:
            errors.append(error)
        else:
            resolved_good.append(resolved)

    resolved_bad: list[dict] = []
    for i, entry in enumerate(bad):
        resolved, error = _resolve_one(entry, "known_bad_shoes", i, catalog)
        if error is not None:
            errors.append(error)
        else:
            resolved_bad.append(resolved)

    good_by_id = {r["shoe_id"]: r for r in resolved_good}
    bad_by_id = {r["shoe_id"]: r for r in resolved_bad}
    contradictions = set(good_by_id) & set(bad_by_id)
    if contradictions:
        named = ", ".join(
            f"{good_by_id[shoe_id]['brand']} {good_by_id[shoe_id]['model']}"
            for shoe_id in sorted(contradictions)
        )
        errors.append(
            f"contradictory input: {named} appear in both known_good_shoes and "
            f"known_bad_shoes"
        )

    return resolved_good, resolved_bad, errors
