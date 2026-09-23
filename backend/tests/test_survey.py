"""[W4'-1] Tests for the survey loading + validation layer: schema.py
(scalar fields + shape), anchors.py (catalog resolution) and store.py
(persistence), against the EXISTING `user_survey` table in
backend/app/db/migrations/0001_init.sql.

Why these exist
----------------
This card is the ONLY writer for schema.py/anchors.py/store.py, and the table
it validates against already exists with its own CHECK constraints -- so the
central risk is not "does validation work" but "does it stay true to the SQL
it did not write". Section A below parses the CHECK constraints back out of
0001_init.sql the way catalog/validate.py pins ENUMS to the schema, so a
hand-edited Python vocabulary that drifts from the migration fails a test
instead of failing silently at INSERT time.

The default suite (this file, minus the DB-backed section at the bottom) runs
with no network and no database: anchor resolution is exercised against
`anchors.StaticCatalog`, an in-memory fake, exactly like
`QuotaLedger.in_memory()` in scraping/collector.py. The DB-backed section
additionally exercises the real seeded catalog and a real INSERT, and skips
cleanly (not an error) when no database is reachable.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

SURVEY_DIR = Path(__file__).resolve().parents[1] / "app" / "survey"
MIGRATION = Path(__file__).resolve().parents[1] / "app" / "db" / "migrations" / "0001_init.sql"

sys.path.insert(0, str(SURVEY_DIR))
import anchors as A   # noqa: E402
import schema as S    # noqa: E402
import store as ST    # noqa: E402


# ==========================================================================
# A. The enum vocabulary must not drift from 0001_init.sql (acceptance 1)
# ==========================================================================
#
# Mirrors catalog/validate.py's own comment: "Mirrors the CHECK constraints in
# 0001_init.sql. If these drift apart, the seed load fails at the database
# instead of here, which is a worse place." Parsed from the migration text
# itself, not retyped by hand, so a future edit to either side is caught.

def _user_survey_block() -> str:
    text = MIGRATION.read_text()
    match = re.search(r"CREATE TABLE user_survey \((.*?)\n\);", text, re.DOTALL)
    assert match, "could not find the user_survey table definition in 0001_init.sql"
    return match.group(1)


def _nullable_enum_checks(sql_block: str) -> dict[str, set[str]]:
    """Parse every `CHECK (col IS NULL OR col IN (...))` constraint in `sql_block`."""
    pattern = re.compile(r"CHECK\s*\(\s*(\w+)\s+IS NULL OR\s+\1\s+IN\s*\(([^)]*)\)\s*\)")
    found: dict[str, set[str]] = {}
    for column, values in pattern.findall(sql_block):
        found[column] = set(re.findall(r"'([^']*)'", values))
    return found


SQL_BLOCK = _user_survey_block()
SQL_NULLABLE_ENUMS = _nullable_enum_checks(SQL_BLOCK)


def test_sql_block_actually_contains_the_five_expected_constraints():
    """Sanity check on the parser itself: if this fails, the regex is wrong,
    not the schema -- every other test in this section would otherwise pass
    vacuously by comparing two empty dicts."""
    assert set(SQL_NULLABLE_ENUMS) == {
        "foot_width", "instep", "toe_shape", "arch", "discipline",
    }


@pytest.mark.parametrize("field", sorted(S.ENUMS))
def test_python_enum_matches_the_sql_check_exactly(field):
    """Would fail if schema.ENUMS drifted from 0001_init.sql in either
    direction: a value added to one side and not the other."""
    assert field in SQL_NULLABLE_ENUMS, f"schema.ENUMS has {field!r}, but no matching CHECK exists"
    assert S.ENUMS[field] == SQL_NULLABLE_ENUMS[field], (
        f"{field}: schema.py says {sorted(S.ENUMS[field])}, "
        f"0001_init.sql says {sorted(SQL_NULLABLE_ENUMS[field])}"
    )


def test_no_sql_check_covers_a_field_schema_does_not_mirror():
    """The reverse direction: every nullable-enum CHECK in user_survey must be
    represented in schema.ENUMS, or a real constraint would silently go
    unvalidated in Python."""
    assert set(SQL_NULLABLE_ENUMS) == set(S.ENUMS)


# ==========================================================================
# B. heel_fit / terrain / level: Python-only vocabulary (acceptance 2)
# ==========================================================================

def test_heel_fit_terrain_level_have_no_matching_sql_check():
    """Confirms the drift this module's comments claim is real, so the claim
    cannot go stale silently. If a future migration adds these constraints,
    this test starts failing and is the signal to delete the Python-only
    vocabulary comment, not to "fix" the test."""
    assert set(SQL_NULLABLE_ENUMS).isdisjoint({"heel_fit", "terrain", "level"})
    assert set(S.PY_ONLY_ENUMS) == {"heel_fit", "terrain", "level"}


@pytest.mark.parametrize(
    "field,value",
    [
        ("heel_fit", "narrow"), ("heel_fit", "medium"), ("heel_fit", "wide"),
        ("terrain", "slab"), ("terrain", "vertical"),
        ("terrain", "overhang"), ("terrain", "crack"),
        ("level", "beginner"), ("level", "intermediate"),
        ("level", "advanced"), ("level", "elite"),
    ],
)
def test_py_only_enum_accepts_each_documented_value(field, value):
    assert S.validate({field: value}) == []


@pytest.mark.parametrize("field", ["heel_fit", "terrain", "level"])
def test_py_only_enum_rejects_a_value_outside_its_vocabulary(field):
    errors = S.validate({field: "nonsense"})
    assert len(errors) == 1
    assert field in errors[0] and "nonsense" in errors[0]


@pytest.mark.parametrize("field", sorted(set(S.ENUMS) | set(S.PY_ONLY_ENUMS)))
def test_enum_field_rejects_a_non_string_type(field):
    """Every enum field (SQL-backed or Python-only) must reject a non-string
    value distinctly from an out-of-vocabulary string -- e.g. an integer
    grade accidentally sent where a category string belongs."""
    errors = S.validate({field: 3})
    assert len(errors) == 1
    assert f"{field} must be a string, got int" == errors[0]


# ==========================================================================
# C. street_size fits NUMERIC(4,1) and is plausible (acceptance 3)
# ==========================================================================

def test_street_size_accepts_a_plausible_value():
    assert S.validate({"street_size": 10.5}) == []


def test_street_size_rejects_bool_even_though_bool_is_an_int_subclass():
    """The validate.py trap, applied here: isinstance(True, int) is True in
    Python, so a naive numeric check would silently accept a boolean."""
    errors = S.validate({"street_size": True})
    assert len(errors) == 1
    assert "street_size must be a number, got bool" == errors[0]


def test_street_size_rejects_a_numeric_string():
    errors = S.validate({"street_size": "10.5"})
    assert len(errors) == 1
    assert "got str" in errors[0]


def test_street_size_rejects_a_value_that_does_not_fit_numeric_4_1():
    """1200.5 has one decimal place and would pass a naive range check
    against the plausibility band's mechanism, but the DDL column itself
    (NUMERIC(4,1)) cannot hold a value this large -- this must be its own,
    specifically-worded failure, not folded into the plausibility message."""
    errors = S.validate({"street_size": 1200.5})
    assert len(errors) == 1
    assert "does not fit NUMERIC(4,1)" in errors[0]


def test_street_size_rejects_more_than_one_decimal_place():
    errors = S.validate({"street_size": 10.55})
    assert len(errors) == 1
    assert "more than 1 decimal place" not in errors[0]  # exact wording below
    assert "at most 1 decimal place" in errors[0]


def test_street_size_rejects_an_implausible_but_column_valid_value():
    """500.0 fits NUMERIC(4,1) exactly (one implicit decimal place, well
    under 1000) but is not a real street shoe size -- must fail the
    plausibility band specifically, proving the two checks are independent."""
    errors = S.validate({"street_size": 500.0})
    assert len(errors) == 1
    assert "outside the plausible range" in errors[0]


def test_street_size_rejects_zero_and_negative():
    for value in (0, -5.0):
        errors = S.validate({"street_size": value})
        assert len(errors) == 1
        assert "outside the plausible range" in errors[0]


def test_street_size_none_is_accepted_and_key_may_be_absent():
    assert S.validate({"street_size": None}) == []
    assert S.validate({}) == []


@pytest.mark.parametrize(
    "value,expect_ok",
    [(20, True), (20.0, True), (20.1, False), (0.1, True)],
    ids=["upper-boundary-int", "upper-boundary-float", "just-above-upper", "just-above-lower"],
)
def test_street_size_plausibility_band_boundaries(value, expect_ok):
    errors = S.validate({"street_size": value})
    assert (errors == []) is expect_ok, f"street_size={value}: {errors}"


# ==========================================================================
# D. goal_x_target / goal_y_target / budget_cap_usd -- defence in depth
#    mirroring survey_target_x / survey_target_y (the SQL already checks
#    these; validating in Python too matches catalog/validate.py's own
#    practice of checking prior ranges even though the DB also enforces them)
# ==========================================================================

@pytest.mark.parametrize("field", ["goal_x_target", "goal_y_target"])
def test_goal_target_accepts_the_boundary_values(field):
    assert S.validate({field: -1}) == []
    assert S.validate({field: 1}) == []


@pytest.mark.parametrize("field", ["goal_x_target", "goal_y_target"])
def test_goal_target_rejects_outside_the_quadrant_plane(field):
    errors = S.validate({field: 1.5})
    assert len(errors) == 1
    assert "survey_target_x / survey_target_y" in errors[0]


def test_budget_cap_rejects_zero_as_a_judgement_call():
    """Not SQL-enforced (0001_init.sql puts no CHECK on budget_cap_usd); a
    zero cap would fail every shoe against the section 7.6 budget gate, which
    is worth rejecting at submission time rather than silently later."""
    errors = S.validate({"budget_cap_usd": 0})
    assert len(errors) == 1
    assert "budget_cap_usd" in errors[0]


def test_budget_cap_rejects_a_value_outside_numeric_7_2():
    errors = S.validate({"budget_cap_usd": 250_000})
    assert len(errors) == 1
    assert "NUMERIC(7,2)" in errors[0]


def test_budget_cap_accepts_a_plausible_value():
    assert S.validate({"budget_cap_usd": 180.0}) == []


@pytest.mark.parametrize(
    "value,expect_ok",
    [(99999.99, True), (100_000, False), (0.01, True)],
    ids=["just-below-numeric-7-2-limit", "at-numeric-7-2-limit", "just-above-zero"],
)
def test_budget_cap_numeric_7_2_boundaries(value, expect_ok):
    errors = S.validate({"budget_cap_usd": value})
    assert (errors == []) is expect_ok, f"budget_cap_usd={value}: {errors}"


# ==========================================================================
# E. Unknown/extra top-level keys are rejected (D4, acceptance 6)
# ==========================================================================

def test_unknown_top_level_key_is_rejected_by_name():
    """An email address must never be able to ride along into storage."""
    errors = S.validate({"email": "climber@example.com", "foot_width": "narrow"})
    assert len(errors) == 1
    assert "email" in errors[0]


def test_every_real_column_name_is_allowed():
    for field in S.SCALAR_FIELDS + S.ANCHOR_FIELDS:
        assert S.validate({field: None if field not in S.ANCHOR_FIELDS else []}) == []


def test_payload_must_be_a_mapping():
    errors = S.validate(["not", "a", "mapping"])
    assert len(errors) == 1
    assert "must be a mapping" in errors[0]


def test_anchor_field_must_be_a_list_not_e_g_a_single_dict():
    """Mirrors survey_anchors_array's jsonb_typeof(...) = 'array' check."""
    errors = S.validate({"known_good_shoes": {"brand": "Scarpa", "model": "Drago"}})
    assert len(errors) == 1
    assert "survey_anchors_array" in errors[0]


@pytest.mark.parametrize("field", ["known_good_shoes", "known_bad_shoes"])
def test_explicit_null_anchor_field_is_rejected_not_treated_as_omitted(field):
    """known_good_shoes/known_bad_shoes are NOT NULL in 0001_init.sql (DEFAULT
    '[]'::jsonb). An OMITTED key defaults to [] downstream in store.py, but an
    EXPLICIT JSON null is a distinct, invalid input and must be rejected, not
    silently coerced to the same default."""
    errors = S.validate({field: None})
    assert len(errors) == 1
    assert f"{field} must be a list, got NoneType" in errors[0]


# ==========================================================================
# F. Anchor resolution against the catalog (acceptance 4)
# ==========================================================================
#
# StaticCatalog fixture mirrors the REAL seeded data (verified against
# backend/app/catalog/data/shoes.yaml and, in section H below, the live
# database): La Sportiva Solution (base vs Comp), La Sportiva Katana (Lace vs
# Velcro) and Scarpa Instinct (VS vs VSR) all share (brand, model) and differ
# only by `version`. Instinct VSR and the base Solution are section 3
# calibration anchors -- exactly the two the task calls out as a correctness
# risk if resolution ever silently picked one.

def _catalog() -> A.StaticCatalog:
    shoes = [
        A.CatalogShoe("id-solution-base", "La Sportiva", "Solution", "", "unisex"),
        A.CatalogShoe("id-solution-comp", "La Sportiva", "Solution", "Comp", "unisex"),
        A.CatalogShoe("id-katana-lace", "La Sportiva", "Katana", "Lace", "unisex"),
        A.CatalogShoe("id-katana-velcro", "La Sportiva", "Katana", "Velcro", "unisex"),
        A.CatalogShoe("id-instinct-vs", "Scarpa", "Instinct", "VS", "unisex"),
        A.CatalogShoe("id-instinct-vsr", "Scarpa", "Instinct", "VSR", "unisex"),
        A.CatalogShoe("id-drago", "Scarpa", "Drago", "", "unisex"),
        A.CatalogShoe("id-defy", "Evolv", "Defy", "", "mens"),
        A.CatalogShoe("id-elektra", "Evolv", "Defy", "", "womens"),  # same (brand,model), gender differs
    ]
    # Exactly the real alias set for these six rows (confirmed against the
    # live database: no bare "Katana" or "Instinct" alias exists for either
    # sibling; "Solution" is registered ONLY for the base).
    aliases = {
        "Solution": "id-solution-base",
        "LS Solution": "id-solution-base",
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


def test_unknown_brand_model_pair_is_rejected_naming_the_pair():
    resolved, err = A._resolve_one({"brand": "Nike", "model": "Air Max"}, "known_good_shoes", 0, _catalog())
    assert resolved is None
    assert "Nike" in err and "Air Max" in err and "unknown" in err.lower()


@pytest.mark.parametrize(
    "brand,model,expect_in_error",
    [
        ("Scarpa", "Instinct", ("VS", "VSR")),
        ("La Sportiva", "Katana", ("Lace", "Velcro")),
        ("La Sportiva", "Solution", ("''", "Comp")),
    ],
    ids=["scarpa-instinct", "la-sportiva-katana", "la-sportiva-solution"],
)
def test_ambiguous_brand_model_pair_is_rejected_never_silently_picked(brand, model, expect_in_error):
    """The three pairs the task names as real in the live data. Two of the
    six rows involved (Instinct VSR, base Solution) are section 3 calibration
    anchors, so a silent pick here would corrupt calibration-grade input."""
    resolved, err = A._resolve_one({"brand": brand, "model": model}, "known_good_shoes", 0, _catalog())
    assert resolved is None
    assert "ambiguous" in err.lower()
    for token in expect_in_error:
        assert token in err, f"expected {token!r} listed among the candidates in: {err}"


def test_ambiguous_pair_disambiguated_by_explicit_version():
    resolved, err = A._resolve_one(
        {"brand": "Scarpa", "model": "Instinct", "version": "VSR"}, "known_good_shoes", 0, _catalog()
    )
    assert err is None
    assert resolved["shoe_id"] == "id-instinct-vsr"


def test_ambiguous_pair_disambiguated_by_explicit_empty_version_selects_the_base():
    """version='' is how the DDL represents "no version suffix" (shoe.version
    is NOT NULL DEFAULT ''), so it must be a valid, meaningful disambiguator
    distinct from omitting `version` entirely."""
    resolved, err = A._resolve_one(
        {"brand": "La Sportiva", "model": "Solution", "version": ""}, "known_good_shoes", 0, _catalog()
    )
    assert err is None
    assert resolved["shoe_id"] == "id-solution-base"


def test_ambiguous_pair_disambiguated_by_gender():
    resolved, err = A._resolve_one(
        {"brand": "Evolv", "model": "Defy", "gender": "womens"}, "known_good_shoes", 0, _catalog()
    )
    assert err is None
    assert resolved["shoe_id"] == "id-elektra"


@pytest.mark.parametrize(
    "model_as_typed,expected_id",
    [
        ("Solution Comp", "id-solution-comp"),
        ("Katana Lace", "id-katana-lace"),
        ("Katana Velcro", "id-katana-velcro"),
        ("Instinct VS", "id-instinct-vs"),
        ("VSR", "id-instinct-vsr"),
    ],
)
def test_alias_surface_form_is_an_unambiguous_disambiguation_path(model_as_typed, expected_id):
    """These strings do not match any raw shoe.model column value, so identity
    match returns zero candidates and the globally-unique alias index
    resolves them outright -- no version/gender needed."""
    brand = "Scarpa" if "Instinct" in model_as_typed or model_as_typed == "VSR" else "La Sportiva"
    resolved, err = A._resolve_one({"brand": brand, "model": model_as_typed}, "known_good_shoes", 0, _catalog())
    assert err is None, f"expected {model_as_typed!r} to resolve unambiguously, got error: {err}"
    assert resolved["shoe_id"] == expected_id


def test_resolution_is_case_insensitive():
    resolved, err = A._resolve_one({"brand": "SCARPA", "model": "drago"}, "known_good_shoes", 0, _catalog())
    assert err is None
    assert resolved["shoe_id"] == "id-drago"


def test_size_is_opaque_to_the_catalog_but_not_unconstrained():
    """D9 / the DDL comment: size is never gated against shoe_size_map -- a
    size the catalog has never heard of still resolves, because sizing is a
    soft warning decided downstream, not a hard gate here.

    "Opaque" means the CATALOG does not interpret it. It does not mean
    unvalidated: the security review of this card showed an unconstrained
    free-text field is how a direct identifier reaches user_survey, so the
    charset allow-list applies (see section K). Both halves are pinned here
    so neither can be weakened without the other being noticed."""
    unlisted = "EU 43 2/3"  # not in shoe_size_map -- which is empty anyway
    resolved, err = A._resolve_one(
        {"brand": "Scarpa", "model": "Drago", "size": unlisted},
        "known_good_shoes", 0, _catalog(),
    )
    assert err is None, f"size must not be gated against the catalog: {err}"
    assert resolved["size"] == unlisted


def test_size_omitted_entirely_still_resolves():
    resolved, err = A._resolve_one({"brand": "Scarpa", "model": "Drago"}, "known_good_shoes", 0, _catalog())
    assert err is None
    assert "size" not in resolved


def test_non_string_size_is_rejected():
    resolved, err = A._resolve_one(
        {"brand": "Scarpa", "model": "Drago", "size": 42}, "known_good_shoes", 0, _catalog()
    )
    assert resolved is None
    assert "'size' must be a string" in err


def test_non_string_version_is_rejected():
    resolved, err = A._resolve_one(
        {"brand": "Scarpa", "model": "Instinct", "version": 2}, "known_good_shoes", 0, _catalog()
    )
    assert resolved is None
    assert "'version' must be a string" in err


def test_shoe_id_supplied_by_the_caller_is_rejected():
    """shoe_id is the OUTPUT of resolution; accepting it as input would let a
    caller point an anchor at an arbitrary shoe without ever matching it."""
    resolved, err = A._resolve_one(
        {"brand": "Scarpa", "model": "Drago", "shoe_id": "attacker-supplied"},
        "known_good_shoes", 0, _catalog(),
    )
    assert resolved is None
    assert "shoe_id" in err and "must not be supplied" in err


def test_unknown_key_inside_an_anchor_entry_is_rejected():
    """The same D4 discipline as schema.ALLOWED_KEYS, applied one level down
    -- an identifier must not be smuggled inside an anchor entry either."""
    resolved, err = A._resolve_one(
        {"brand": "Scarpa", "model": "Drago", "owner_email": "x@example.com"},
        "known_good_shoes", 0, _catalog(),
    )
    assert resolved is None
    assert "owner_email" in err


def test_non_dict_anchor_entry_is_rejected():
    resolved, err = A._resolve_one("Scarpa Drago", "known_good_shoes", 2, _catalog())
    assert resolved is None
    assert "known_good_shoes[2]" in err and "must be a mapping" in err


@pytest.mark.parametrize("missing_field", ["brand", "model"])
def test_missing_required_field_is_rejected(missing_field):
    entry = {"brand": "Scarpa", "model": "Drago"}
    del entry[missing_field]
    resolved, err = A._resolve_one(entry, "known_good_shoes", 0, _catalog())
    assert resolved is None
    assert f"'{missing_field}'" in err and "required" in err


def test_invalid_gender_value_is_rejected():
    resolved, err = A._resolve_one(
        {"brand": "Evolv", "model": "Defy", "gender": "child"}, "known_good_shoes", 0, _catalog()
    )
    assert resolved is None
    assert "'gender'" in err


def test_same_shoe_in_both_good_and_bad_is_rejected_as_contradictory():
    """Each entry resolves individually clean (that is the point -- this is
    not an unknown or ambiguous shoe), so the contradiction can only be
    caught by comparing the two resolved sets, which is why `errors` -- not
    the resolved lists themselves -- is the contract callers must check."""
    good = [{"brand": "Scarpa", "model": "Drago"}]
    bad = [{"brand": "SCARPA", "model": "DRAGO"}]  # same shoe, different case
    _, _, errors = A.resolve_anchors(good, bad, _catalog())
    assert len(errors) == 1
    assert "contradictory" in errors[0].lower() and "Drago" in errors[0]

    # And the important end-to-end guarantee: build_survey_row() must never
    # hand back a row when resolve_anchors() reported any error at all.
    payload = {"known_good_shoes": good, "known_bad_shoes": bad}
    row, build_errors = ST.build_survey_row(payload, _catalog())
    assert row is None
    assert build_errors == errors


def test_resolve_anchors_accumulates_errors_from_both_lists_independently():
    """One bad anchor in G must not hide a bad anchor in B."""
    good = [{"brand": "Nike", "model": "Air Max"}]
    bad = [{"brand": "Scarpa", "model": "Instinct"}]  # ambiguous
    _, _, errors = A.resolve_anchors(good, bad, _catalog())
    assert len(errors) == 2
    assert any("Nike" in e for e in errors)
    assert any("ambiguous" in e.lower() for e in errors)


def test_resolve_anchors_fills_in_shoe_id_on_every_resolved_entry():
    good = [{"brand": "Scarpa", "model": "Drago", "size": "42"}]
    resolved_good, resolved_bad, errors = A.resolve_anchors(good, [], _catalog())
    assert errors == []
    assert resolved_good == [{"brand": "Scarpa", "model": "Drago", "size": "42", "shoe_id": "id-drago"}]
    assert resolved_bad == []


def test_known_good_shoes_not_a_list_is_reported_without_crashing():
    resolved_good, resolved_bad, errors = A.resolve_anchors({"brand": "x"}, [], _catalog())
    assert resolved_good == [] and resolved_bad == []
    assert len(errors) == 1
    assert "known_good_shoes must be a list" in errors[0]


@pytest.mark.parametrize("bad_value", [None, [], 42, True])
def test_non_dict_anchor_entry_variants_are_rejected_without_crashing(bad_value):
    """None, a nested list, a number and a boolean are all "not a mapping" --
    none of them should raise (e.g. AttributeError from a bare `.get()`)."""
    resolved, err = A._resolve_one(bad_value, "known_good_shoes", 0, _catalog())
    assert resolved is None
    assert "must be a mapping" in err


@pytest.mark.parametrize("blank", ["", "   "])
def test_empty_or_whitespace_only_brand_and_model_are_rejected(blank):
    resolved, err = A._resolve_one({"brand": blank, "model": "Drago"}, "known_good_shoes", 0, _catalog())
    assert resolved is None and "'brand'" in err and "required" in err

    resolved, err = A._resolve_one({"brand": "Scarpa", "model": blank}, "known_good_shoes", 0, _catalog())
    assert resolved is None and "'model'" in err and "required" in err


def test_unicode_and_emoji_in_size_are_rejected_cleanly_not_by_crashing():
    """Robustness to Unicode/emoji. Since the security review, emoji in
    `size` is REJECTED rather than stored -- but the distinction that matters
    is that it is rejected by a named validation error, never by an exception
    escaping from deep inside psycopg's encoder."""
    resolved, err = A._resolve_one(
        {"brand": "Scarpa", "model": "Drago", "size": "42 ♦ \U0001F9E6 café"},
        "known_good_shoes", 0, _catalog(),
    )
    assert resolved is None
    assert "brand size" in err and "known_good_shoes[0]" in err


def test_a_non_ascii_but_legitimate_size_still_resolves():
    """The charset allow-list is not an ASCII-only rule: the vulgar fractions
    brands actually print must survive it."""
    resolved, err = A._resolve_one(
        {"brand": "Scarpa", "model": "Drago", "size": "42 ½"},
        "known_good_shoes", 0, _catalog(),
    )
    assert err is None, err
    assert resolved["size"] == "42 ½"


def test_case_insensitive_match_handles_unicode_case_folding():
    """La Sportiva vs LA SPORTIVA vs an accented variant of a matching brand
    -- `_key()` uses str.lower(), which Python applies Unicode-aware."""
    catalog = A.StaticCatalog(
        [A.CatalogShoe("id-1", "Café Brand", "ModelÉ", "", "unisex")]
    )
    resolved, err = A._resolve_one(
        {"brand": "CAFÉ BRAND", "model": "modelé"}, "known_good_shoes", 0, catalog
    )
    assert err is None
    assert resolved["shoe_id"] == "id-1"


def test_a_large_anchor_list_resolves_without_crashing_or_pathological_slowdown():
    """Not a realistic submission (a user has a handful of anchors, not
    thousands), but resolve_anchors() itself must not crash or hang on one.

    resolve_anchors deliberately carries NO count cap: it is a pure function
    over an injected catalog, and the cap is a submission policy, enforced in
    schema.validate() / build_survey_row() (section K) so an oversized list is
    rejected before any catalog round trip happens."""
    import time

    good = [{"brand": "Scarpa", "model": "Drago"} for _ in range(2000)]
    bad = [{"brand": "Evolv", "model": "Defy", "gender": "mens"} for _ in range(2000)]

    started = time.monotonic()
    resolved_good, resolved_bad, errors = A.resolve_anchors(good, bad, _catalog())
    elapsed = time.monotonic() - started

    assert len(resolved_good) == 2000 and len(resolved_bad) == 2000
    assert errors == []
    assert elapsed < 5.0, f"resolving 4000 anchors took {elapsed:.2f}s -- looks quadratic"


# ==========================================================================
# G. All-NULL fit profile with anchors alone is ACCEPTED (acceptance 5)
# ==========================================================================
#
# First-class test per the task: section 7.1 explicitly allows shipping fit
# v0 on anchors alone, so this is not an edge case to tolerate but a case to
# actively prove.

def test_anchors_alone_with_every_other_field_absent_is_a_valid_submission():
    payload = {"known_good_shoes": [{"brand": "Scarpa", "model": "Drago"}]}
    assert S.validate(payload) == []

    row, errors = ST.build_survey_row(payload, _catalog())
    assert errors == []
    assert row["known_good_shoes"] == [{"brand": "Scarpa", "model": "Drago", "shoe_id": "id-drago"}]
    assert row["known_bad_shoes"] == []
    for field in S.SCALAR_FIELDS:
        assert row[field] is None, f"{field} should be untouched (None), not defaulted to a guess"


def test_completely_empty_submission_is_also_valid():
    """No fit fields AND no anchors. Still a legal (if useless) submission --
    the DDL makes every fit/anchor field optional."""
    row, errors = ST.build_survey_row({}, _catalog())
    assert errors == []
    assert row["known_good_shoes"] == [] and row["known_bad_shoes"] == []


# ==========================================================================
# H. Token generation: secrets.token_urlsafe, never random/uuid4/timestamp
# ==========================================================================

def test_new_survey_token_calls_secrets_token_urlsafe(monkeypatch):
    calls = []

    def fake_token_urlsafe(n):
        calls.append(n)
        return "x" * n

    monkeypatch.setattr(ST.secrets, "token_urlsafe", fake_token_urlsafe)
    token = ST.new_survey_token()
    assert calls, "new_survey_token() must call secrets.token_urlsafe (a CSPRNG)"
    assert token == "x" * calls[0]


def test_new_survey_token_is_unique_across_calls_and_reasonably_long():
    a, b = ST.new_survey_token(), ST.new_survey_token()
    assert a != b
    assert len(a) >= 32


# ==========================================================================
# I. build_survey_row: end-to-end orchestration (schema + anchors combined)
# ==========================================================================

def test_build_survey_row_rejects_unknown_top_level_key_and_returns_no_row():
    row, errors = ST.build_survey_row({"email": "x@example.com"}, _catalog())
    assert row is None
    assert any("email" in e for e in errors)


def test_build_survey_row_combines_scalar_and_anchor_errors_in_one_pass():
    payload = {
        "foot_width": "extra-wide",  # invalid enum
        "known_good_shoes": [{"brand": "Nike", "model": "Air Max"}],  # unknown shoe
    }
    row, errors = ST.build_survey_row(payload, _catalog())
    assert row is None
    assert len(errors) == 2
    assert any("foot_width" in e for e in errors)
    assert any("Nike" in e for e in errors)


def test_build_survey_row_full_valid_submission():
    payload = {
        "foot_width": "narrow",
        "instep": "medium",
        "toe_shape": "egyptian",
        "arch": "high",
        "heel_fit": "wide",
        "street_size": 9.5,
        "discipline": "boulder",
        "terrain": "overhang",
        "level": "advanced",
        "goal_x_target": 0.5,
        "goal_y_target": 0.5,
        "budget_cap_usd": 200.0,
        "known_good_shoes": [{"brand": "Scarpa", "model": "Drago"}],
        "known_bad_shoes": [{"brand": "Evolv", "model": "Defy", "gender": "mens"}],
    }
    row, errors = ST.build_survey_row(payload, _catalog())
    assert errors == []
    assert row["foot_width"] == "narrow"
    assert row["street_size"] == 9.5
    assert row["known_good_shoes"][0]["shoe_id"] == "id-drago"
    assert row["known_bad_shoes"][0]["shoe_id"] == "id-defy"
    assert isinstance(row["survey_token"], str) and len(row["survey_token"]) >= 32


# ==========================================================================
# J. insert_survey: parameterised, one transaction, --dry-run rolls back
#    (hermetic: a fake connection/cursor, no database)
# ==========================================================================

class _FakeCursor:
    def __init__(self, calls):
        self._calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def execute(self, sql, params=None):
        self._calls.append((sql, params))


class _FakeConn:
    def __init__(self):
        self.calls = []
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return _FakeCursor(self.calls)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def _minimal_row(token="TOKEN_MARKER_XYZ"):
    row = {field: None for field in S.SCALAR_FIELDS}
    row["known_good_shoes"] = [{"brand": "Scarpa", "model": "Drago", "shoe_id": "id-drago"}]
    row["known_bad_shoes"] = []
    row["survey_token"] = token
    return row


def test_insert_survey_commits_when_not_dry_run():
    conn = _FakeConn()
    ST.insert_survey(conn, _minimal_row(), dry_run=False)
    assert conn.committed is True
    assert conn.rolled_back is False


def test_insert_survey_rolls_back_on_dry_run():
    conn = _FakeConn()
    ST.insert_survey(conn, _minimal_row(), dry_run=True)
    assert conn.rolled_back is True
    assert conn.committed is False


def test_insert_survey_is_parameterised_not_f_string_interpolated():
    """The house rule (catalog/seed.py): %(name)s binding, never a value
    spliced into the SQL text. A marker token that does NOT appear in the SQL
    string itself, but DOES appear in the params dict, proves it."""
    conn = _FakeConn()
    row = _minimal_row(token="TOKEN_MARKER_XYZ")
    ST.insert_survey(conn, row, dry_run=True)

    assert len(conn.calls) == 1
    sql, params = conn.calls[0]
    assert "%(survey_token)s" in sql
    assert "TOKEN_MARKER_XYZ" not in sql, "a literal value leaked into the SQL text"
    assert params["survey_token"] == "TOKEN_MARKER_XYZ"


def test_insert_survey_wraps_anchor_lists_for_jsonb():
    from psycopg.types.json import Jsonb

    conn = _FakeConn()
    row = _minimal_row()
    ST.insert_survey(conn, row, dry_run=True)
    _, params = conn.calls[0]
    assert isinstance(params["known_good_shoes"], Jsonb)
    assert isinstance(params["known_bad_shoes"], Jsonb)


def test_insert_columns_cover_every_scalar_and_anchor_field_plus_token():
    assert set(ST.INSERT_COLUMNS) == {"survey_token"} | set(S.SCALAR_FIELDS) | set(S.ANCHOR_FIELDS)


# ==========================================================================
# K. DB-backed tests -- skip cleanly when no database is reachable.
#    Every test here rolls back; none ever commits, so user_survey is
#    guaranteed empty afterwards even if an assertion fails mid-test.
# ==========================================================================

def _database_url() -> str:
    import os

    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
        from config import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    return os.environ.get("DATABASE_URL", "postgresql://localhost/cruxup")


@pytest.fixture()
def db_conn():
    try:
        import psycopg
    except ImportError:
        pytest.skip("psycopg not installed; DB-backed tests are optional")
        return

    try:
        conn = psycopg.connect(_database_url())
    except psycopg.OperationalError:
        pytest.skip("no reachable database at DATABASE_URL; DB-backed tests are optional")
        return

    try:
        yield conn
    finally:
        # Always undo, whether or not the test body already did -- this must
        # run even when an assertion above raised, so user_survey never
        # carries test residue in the shared local database.
        conn.rollback()
        conn.close()


def test_db_shoe_size_map_is_currently_empty(db_conn):
    """Confirms the precondition this whole module's design leans on: D9
    makes size_exists the only hard gate, and that is moot if the table
    already had rows this module would need to reason about."""
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM shoe_size_map")
        (count,) = cur.fetchone()
    assert count == 0


def test_db_scarpa_instinct_is_genuinely_ambiguous_in_the_live_catalog(db_conn):
    catalog = A.PostgresCatalog(db_conn)
    resolved, err = A._resolve_one({"brand": "Scarpa", "model": "Instinct"}, "known_good_shoes", 0, catalog)
    assert resolved is None
    assert "ambiguous" in err.lower() and "VS" in err and "VSR" in err


def test_db_instinct_vsr_resolves_via_version_to_a_real_shoe_id(db_conn):
    catalog = A.PostgresCatalog(db_conn)
    resolved, err = A._resolve_one(
        {"brand": "Scarpa", "model": "Instinct", "version": "VSR"}, "known_good_shoes", 0, catalog
    )
    assert err is None
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM shoe WHERE brand='Scarpa' AND model='Instinct' AND version='VSR'"
        )
        (real_id,) = cur.fetchone()
    assert resolved["shoe_id"] == str(real_id)


def test_db_solution_comp_resolves_via_alias_to_a_real_shoe_id(db_conn):
    catalog = A.PostgresCatalog(db_conn)
    resolved, err = A._resolve_one(
        {"brand": "La Sportiva", "model": "Solution Comp"}, "known_good_shoes", 0, catalog
    )
    assert err is None
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM shoe WHERE brand='La Sportiva' AND model='Solution' AND version='Comp'"
        )
        (real_id,) = cur.fetchone()
    assert resolved["shoe_id"] == str(real_id)


def test_db_insert_dry_run_round_trips_anchors_through_jsonb_and_leaves_no_row(db_conn):
    """Proves a genuine JSONB round trip: reads the row back INSIDE the
    still-open transaction (Postgres shows a session its own uncommitted
    writes) before rolling back, so nothing is ever committed.

    The anchor is laced with SQL metacharacters -- a single quote and a
    statement terminator -- AFTER validation, by writing them straight into
    the row handed to _insert_row. That is deliberate: the charset allow-list
    added for the security review would now reject those characters at the
    validation layer, but the property under test here belongs to the INSERT,
    not the validator. Injecting past validation proves _insert_row is
    parameterised on its own merits, so the write stays safe even if a future
    caller bypasses or loosens validation.
    """
    catalog = A.PostgresCatalog(db_conn)
    payload = {
        "foot_width": "wide",
        "known_good_shoes": [
            {"brand": "Scarpa", "model": "Drago", "size": "42.5 EU"},
        ],
        "known_bad_shoes": [{"brand": "Evolv", "model": "Defy", "gender": "mens"}],
    }
    row, errors = ST.build_survey_row(payload, catalog)
    assert errors == []

    # Past the validator on purpose -- see the docstring.
    injected = "42.5 EU; O'Brien's pair"
    row["known_good_shoes"][0]["size"] = injected

    with db_conn.cursor() as cur:
        ST._insert_row(cur, row)
        cur.execute(
            "SELECT known_good_shoes, known_bad_shoes FROM user_survey WHERE survey_token = %(survey_token)s",
            {"survey_token": row["survey_token"]},
        )
        good, bad = cur.fetchone()

    assert good == row["known_good_shoes"]
    assert bad == row["known_bad_shoes"]
    assert good[0]["size"] == injected, "SQL metacharacters must survive verbatim"

    # The statement terminator did not end the statement: the catalog is intact.
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM shoe")
        (shoe_count,) = cur.fetchone()
    assert shoe_count == 30, "the injected ';' must not have executed anything"

    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM user_survey WHERE survey_token = %s", (row["survey_token"],))
        (count,) = cur.fetchone()
    assert count == 0, "rollback did not clean up -- a DB test must leave user_survey empty"


def test_db_insert_survey_dry_run_leaves_user_survey_row_count_unchanged(db_conn):
    catalog = A.PostgresCatalog(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM user_survey")
        (before,) = cur.fetchone()

    row, errors = ST.build_survey_row({"known_good_shoes": [{"brand": "Scarpa", "model": "Drago"}]}, catalog)
    assert errors == []
    ST.insert_survey(db_conn, row, dry_run=True)

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM user_survey")
        (after,) = cur.fetchone()
    assert after == before, "a --dry-run insert must not add a row to user_survey"


# ==========================================================================
# L. CLI smoke tests (subprocess) -- error paths and exit codes end to end,
#    the same contract catalog/validate.py and catalog/seed.py commit to.
#    Never touches the real .env/DATABASE_URL for the "no database" cases:
#    each passes --database-url explicitly so the test is deterministic
#    regardless of what is or is not configured in the environment.
# ==========================================================================

SCHEMA_CLI = SURVEY_DIR / "schema.py"
STORE_CLI = SURVEY_DIR / "store.py"


def _run_cli(script: Path, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True, text=True, timeout=30,
    )


def test_cli_schema_exits_1_on_malformed_json(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json")
    result = _run_cli(SCHEMA_CLI, [str(bad)])
    assert result.returncode == 1
    assert "cannot read payload" in result.stderr


def test_cli_schema_exits_1_and_names_the_field_on_a_validation_error(tmp_path):
    payload = tmp_path / "payload.json"
    payload.write_text(json.dumps({"foot_width": "extra-wide"}))
    result = _run_cli(SCHEMA_CLI, [str(payload)])
    assert result.returncode == 1
    assert "foot_width" in result.stdout


def test_cli_schema_exits_0_on_a_valid_submission(tmp_path):
    payload = tmp_path / "payload.json"
    payload.write_text(json.dumps({"foot_width": "narrow", "known_good_shoes": []}))
    result = _run_cli(SCHEMA_CLI, [str(payload)])
    assert result.returncode == 0
    assert "valid" in result.stdout


def test_store_main_exits_2_without_a_database_url(tmp_path, monkeypatch):
    """Deliberately in-process, NOT a subprocess. config.load_dotenv()
    resolves its .env path from config.py's own __file__, independent of the
    subprocess environment -- a scrubbed subprocess env would still silently
    fall back to reading THIS REPO's real .env (which has a real
    DATABASE_URL) and, without --dry-run, could reach a real INSERT. The only
    reliable way to test "no DATABASE_URL anywhere" without touching the real
    .env is to monkeypatch config.DEFAULT_ENV at the object level."""
    payload = tmp_path / "payload.json"
    payload.write_text(json.dumps({"foot_width": "narrow"}))

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
    import config as CFG  # noqa: E402

    empty_env = tmp_path / "empty.env"
    empty_env.write_text("")
    monkeypatch.setattr(CFG, "DEFAULT_ENV", empty_env)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(sys, "argv", ["store.py", str(payload)])

    exit_code = ST.main()
    assert exit_code == 2


def test_cli_store_exits_1_on_a_validation_error_before_ever_connecting(tmp_path):
    payload = tmp_path / "payload.json"
    payload.write_text(json.dumps({"foot_width": "extra-wide"}))
    result = _run_cli(
        STORE_CLI, [str(payload), "--database-url", "postgresql://localhost:1/unreachable", "--dry-run"]
    )
    assert result.returncode == 1
    assert "foot_width" in result.stderr


def test_cli_store_exits_1_on_connection_failure(tmp_path):
    payload = tmp_path / "payload.json"
    payload.write_text(json.dumps({"foot_width": "narrow"}))
    result = _run_cli(
        STORE_CLI, [str(payload), "--database-url", "postgresql://localhost:1/unreachable", "--dry-run"]
    )
    assert result.returncode == 1
    assert "cannot connect" in result.stderr.lower()


def test_cli_store_dry_run_end_to_end_against_the_real_database(db_conn, tmp_path):
    """The one CLI test that needs a real database -- shares db_conn's skip
    behaviour so it is absent from the report, not failing, when no database
    is reachable. Runs the actual script as its own subprocess (its own
    connection, its own process); db_conn is used only afterwards, to confirm
    the subprocess's --dry-run left no residue."""
    payload = tmp_path / "payload.json"
    payload.write_text(json.dumps({
        "foot_width": "narrow",
        "known_good_shoes": [{"brand": "Scarpa", "model": "Drago"}],
    }))
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM user_survey")
        (before,) = cur.fetchone()

    result = _run_cli(STORE_CLI, [str(payload), "--database-url", _database_url(), "--dry-run"])

    assert result.returncode == 0, result.stderr
    assert "[dry run, rolled back] survey_token=" in result.stdout

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM user_survey")
        (after,) = cur.fetchone()
    assert after == before, "the CLI's --dry-run must not add a row to user_survey"


# ==========================================================================
# K. Review findings (W4P1-B/C/D), each pinned by a regression test
# ==========================================================================
#
# Every test below corresponds to a finding from the database / python /
# security review of this card. They exist so a later "simplification" that
# removes a guard fails loudly instead of silently reopening the hole.

# --- D (security), BLOCKING: `size` was an unbounded free-text field --------

def test_oversized_anchor_size_is_rejected():
    """The blocking finding: `size` is the one anchor field the catalog never
    constrains, so without a length cap an arbitrary blob reaches user_survey
    verbatim -- contradicting that table's D4 guarantee. Demonstrated in
    review with a 5 MB string that inserted cleanly."""
    entry = {"brand": "Scarpa", "model": "Drago", "size": "x" * (A.ANCHOR_SIZE_MAX_LEN + 1)}
    resolved, err = A._resolve_one(entry, "known_good_shoes", 0, _catalog())
    assert resolved is None
    assert "'size'" in err and f"maximum {A.ANCHOR_SIZE_MAX_LEN}" in err


def test_an_email_address_no_longer_fits_in_the_size_field():
    """The concrete D4 violation from the review: an identifier riding into
    storage through an ALLOWED key.

    Note a LENGTH cap alone does not catch this -- the address below is 32
    characters, well under ANCHOR_SIZE_MAX_LEN. The charset allow-list is
    what actually rejects it, on '@'."""
    address = "a.person.name@example-domain.com"
    assert len(address) < A.ANCHOR_SIZE_MAX_LEN, "the length cap alone cannot catch this"

    entry = {"brand": "Scarpa", "model": "Drago", "size": address}
    resolved, err = A._resolve_one(entry, "known_good_shoes", 0, _catalog())
    assert resolved is None, "an email address must not reach storage"
    assert "'@'" in err and "D4" in err


def test_a_real_brand_size_string_still_fits_comfortably():
    """The cap must not break legitimate input -- the guard is only useful if
    the values it admits cover real brand sizing."""
    for size in ("42.5", "US M 9.5 / EU 42.5", "UK 8.5", "EU 43 2/3"):
        resolved, err = A._resolve_one(
            {"brand": "Scarpa", "model": "Drago", "size": size}, "known_good_shoes", 0, _catalog()
        )
        assert err is None, f"{size!r} is a real brand size and must be accepted: {err}"
        assert resolved["size"] == size


def test_oversized_brand_and_model_are_rejected_before_reaching_the_catalog():
    for field in ("brand", "model"):
        entry = {"brand": "Scarpa", "model": "Drago", field: "x" * (A.ANCHOR_NAME_MAX_LEN + 1)}
        resolved, err = A._resolve_one(entry, "known_good_shoes", 0, _catalog())
        assert resolved is None
        assert f"maximum {A.ANCHOR_NAME_MAX_LEN}" in err


@pytest.mark.parametrize("field", ["brand", "model", "size", "version"])
def test_nul_byte_is_rejected_with_a_named_error_not_a_psycopg_dataerror(field):
    """A NUL byte cannot be stored in text/jsonb; unguarded it surfaces as an
    untranslatable-character DataError from inside psycopg, which store.main()
    did not catch. Fail closed here instead, by design rather than by crash."""
    entry = {"brand": "Scarpa", "model": "Drago", field: "Dra\x00go"}
    resolved, err = A._resolve_one(entry, "known_good_shoes", 0, _catalog())
    assert resolved is None
    assert "NUL byte" in err


@pytest.mark.parametrize("field", ["brand", "model", "size", "version"])
def test_lone_surrogate_is_rejected_rather_than_raising_unicodeencodeerror(field):
    """A lone UTF-16 surrogate survives json.loads into a Python str but has
    no UTF-8 encoding, so psycopg raised a bare UnicodeEncodeError while
    binding it. Must be a validation error instead."""
    entry = {"brand": "Scarpa", "model": "Drago", field: "Dra\ud800go"}
    resolved, err = A._resolve_one(entry, "known_good_shoes", 0, _catalog())
    assert resolved is None
    assert "lone surrogate" in err


def test_valid_unicode_is_still_accepted_after_the_surrogate_guard():
    """The guard rejects UNENCODABLE text, not non-ASCII text -- a brand with
    an accent must still resolve."""
    catalog = A.StaticCatalog([A.CatalogShoe("id-x", "Añejo", "Piedra", "", "unisex")], {})
    resolved, err = A._resolve_one(
        {"brand": "Añejo", "model": "Piedra", "size": "42 ½"}, "known_good_shoes", 0, catalog
    )
    assert err is None, err
    assert resolved["shoe_id"] == "id-x"


# --- D (security), ADVISORY: no cap on the number of anchors ---------------

def test_too_many_anchors_is_rejected_by_the_shape_pass():
    """Each anchor costs at least one catalog round trip, so an unbounded
    list is unbounded database work from a single submission."""
    payload = {"known_good_shoes": [{"brand": "Scarpa", "model": "Drago"}] * 51}
    errors = S.validate(payload)
    assert len(errors) == 1
    assert f"exceeds the maximum of {S.MAX_ANCHORS_TOTAL}" in errors[0]


def test_the_anchor_cap_counts_both_lists_together():
    """30 + 30 is over the cap even though neither list exceeds it alone."""
    payload = {
        "known_good_shoes": [{"brand": "Scarpa", "model": "Drago"}] * 30,
        "known_bad_shoes": [{"brand": "Evolv", "model": "Defy", "gender": "mens"}] * 30,
    }
    errors = S.validate(payload)
    assert any("exceeds the maximum" in e for e in errors), errors


def test_a_submission_at_the_cap_is_still_accepted():
    payload = {"known_good_shoes": [{"brand": "Scarpa", "model": "Drago"}] * S.MAX_ANCHORS_TOTAL}
    assert S.validate(payload) == []


def test_over_cap_submission_never_reaches_the_catalog():
    """The cap must short-circuit resolution, not merely report alongside it.
    A counting catalog proves no lookup happened -- otherwise the N+1 the cap
    exists to prevent still fires on every rejected submission."""
    class CountingCatalog:
        def __init__(self):
            self.lookups = 0

        def by_identity(self, brand, model):
            self.lookups += 1
            return []

        def by_alias(self, alias):
            self.lookups += 1
            return None

    catalog = CountingCatalog()
    payload = {"known_good_shoes": [{"brand": "Scarpa", "model": "Drago"}] * 200}
    row, errors = ST.build_survey_row(payload, catalog)

    assert row is None
    assert any("exceeds the maximum" in e for e in errors), errors
    assert catalog.lookups == 0, f"{catalog.lookups} catalog lookups on a rejected submission"


# --- B (database) + C (python): NUMERIC scale was unchecked ----------------

@pytest.mark.parametrize("field", ["goal_x_target", "goal_y_target"])
def test_goal_target_rejects_precision_numeric_4_3_would_silently_round(field):
    """Verified in review against live Postgres: '0.1234'::numeric(4,3) is
    stored as 0.123 with NO error. The submission validated clean and was
    stored as a different number, so the scale is checked here."""
    errors = S.validate({field: 0.1234})
    assert len(errors) == 1
    assert "decimal places" in errors[0]


def test_budget_cap_rejects_precision_numeric_7_2_would_silently_round():
    """'123.456'::numeric(7,2) -> 123.46, silently."""
    errors = S.validate({"budget_cap_usd": 199.999})
    assert len(errors) == 1
    assert "decimal places" in errors[0]


@pytest.mark.parametrize("field", ["goal_x_target", "goal_y_target"])
def test_goal_target_tolerates_binary_float_noise(field):
    """The scale check must NOT reject float representation error. q* is
    computed upstream (section 7.5), so 0.1 + 0.2 == 0.30000000000000004 is
    an ordinary value, not a precision mistake. An exact `round(v,n) != v`
    comparison would reject it -- hence SCALE_TOLERANCE."""
    assert S.validate({field: 0.1 + 0.2}) == [], "float noise must not be rejected"
    assert S.validate({field: 0.123}) == []


def test_street_size_scale_check_survived_the_shared_helper_refactor():
    """street_size's own scale check now routes through _scale_error; pin the
    behaviour so the refactor cannot have loosened it."""
    errors = S.validate({"street_size": 10.55})
    assert len(errors) == 1
    assert "at most 1 decimal place" in errors[0]


# --- C (python): load-bearing guard that no test pinned --------------------

def test_build_survey_row_handles_a_non_dict_payload_without_crashing():
    """schema.validate() reports a non-dict but does NOT short-circuit, so
    build_survey_row's isinstance guard is load-bearing: without it,
    payload.get() raises AttributeError instead of returning (None, errors).
    Pinned because the guard reads redundant and invites removal."""
    for payload in (["not", "a", "mapping"], "a string", 42, None):
        row, errors = ST.build_survey_row(payload, _catalog())
        assert row is None, f"{payload!r} must not produce a row"
        assert any("must be a mapping" in e for e in errors), errors


# --- B (database): UniqueViolation escaped both except clauses -------------

def test_unique_violation_is_not_caught_by_the_operational_error_handler():
    """Pins the exception-hierarchy fact the fix rests on: UniqueViolation is
    NOT an OperationalError, so store.main() needed its own handler. If
    psycopg ever reparents it, this fails and the handler can be revisited."""
    psycopg = pytest.importorskip("psycopg")
    assert not issubclass(psycopg.errors.UniqueViolation, psycopg.OperationalError)
    assert issubclass(psycopg.errors.UniqueViolation, psycopg.Error)
    # And the catch-all added below it does cover the DataError family.
    assert issubclass(psycopg.errors.DataError, psycopg.Error)
    assert not issubclass(psycopg.errors.DataError, psycopg.OperationalError)


# --- C (python): return-type annotations were absent -----------------------

def test_the_reviewed_functions_now_declare_their_return_types():
    """The three functions the review named returned undeclared tuples.

    Read from __annotations__ rather than typing.get_type_hints: this repo
    runs Python 3.9, where `from __future__ import annotations` keeps the
    PEP 604 `X | None` syntax valid as a STRING, but get_type_hints would
    evaluate it and raise TypeError on 3.9's `type.__or__`.
    """
    assert "tuple" in ST.build_survey_row.__annotations__["return"]
    assert "tuple" in A.resolve_anchors.__annotations__["return"]
    assert "tuple" in A._resolve_one.__annotations__["return"]
    assert "Iterable" in A.StaticCatalog.__init__.__annotations__["shoes"]


# ==========================================================================
# M. Follow-up review findings, each pinned by a regression test
# ==========================================================================

# --- alias fallback must not override an explicit version/gender -----------

@pytest.mark.parametrize(
    "entry",
    [
        {"brand": "La Sportiva", "model": "Solution", "version": "Comp2"},
        {"brand": "La Sportiva", "model": "Solution", "gender": "womens"},
        {"brand": "Scarpa", "model": "Drago", "version": "XYZ"},
    ],
    ids=["solution-version-comp2", "solution-gender-womens", "drago-version-xyz"],
)
def test_non_matching_explicit_version_or_gender_is_rejected_not_resolved_via_alias(entry):
    """"Solution" and "Drago" are also registered aliases. When the explicit
    version/gender filters out every identity row, the alias fallback used to
    run and accept its hit without those filters -- silently resolving to the
    base Solution (a section 3 calibration anchor) or the Drago."""
    resolved, err = A._resolve_one(entry, "known_good_shoes", 0, _catalog())
    assert resolved is None
    assert "unknown shoe" in err


def test_alias_hit_is_still_narrowed_by_an_explicit_version():
    """The explicit filters apply to whichever candidate set wins, including
    an alias hit: a consistent version still resolves, a conflicting one does
    not."""
    resolved, err = A._resolve_one(
        {"brand": "Scarpa", "model": "VSR", "version": "VSR"}, "known_good_shoes", 0, _catalog()
    )
    assert err is None
    assert resolved["shoe_id"] == "id-instinct-vsr"

    resolved, err = A._resolve_one(
        {"brand": "Scarpa", "model": "VSR", "version": "VS"}, "known_good_shoes", 0, _catalog()
    )
    assert resolved is None
    assert "unknown shoe" in err


# --- PostgresCatalog must strip surrounding whitespace like StaticCatalog ---

@pytest.mark.parametrize(
    "entry,static_id",
    [
        ({"brand": " Scarpa ", "model": "Drago "}, "id-drago"),  # identity path
        ({"brand": "Scarpa", "model": " VSR\t"}, "id-instinct-vsr"),  # alias path
    ],
    ids=["identity", "alias"],
)
def test_db_surrounding_whitespace_resolves_the_same_as_the_static_catalog(db_conn, entry, static_id):
    resolved, err = A._resolve_one(entry, "known_good_shoes", 0, _catalog())
    assert err is None and resolved["shoe_id"] == static_id

    stripped = {k: v.strip() for k, v in entry.items()}
    expected, err = A._resolve_one(stripped, "known_good_shoes", 0, A.PostgresCatalog(db_conn))
    assert err is None

    resolved, err = A._resolve_one(entry, "known_good_shoes", 0, A.PostgresCatalog(db_conn))
    assert err is None, err
    assert resolved["shoe_id"] == expected["shoe_id"]


# --- CLIs decode the payload as JSON bytes, not locale text ----------------

@pytest.mark.parametrize("script", [SCHEMA_CLI, STORE_CLI], ids=["schema", "store"])
def test_cli_exits_1_cleanly_on_invalid_utf8_bytes_not_with_a_traceback(tmp_path, script):
    """UnicodeDecodeError is not a json.JSONDecodeError, so read_text() on
    invalid bytes used to escape the except clause as a traceback."""
    payload = tmp_path / "payload.json"
    payload.write_bytes(b'{"foot_width": "narrow\xff"}')
    args = [str(payload)]
    if script == STORE_CLI:
        args += ["--database-url", "postgresql://localhost:1/unreachable", "--dry-run"]
    result = _run_cli(script, args)
    assert result.returncode == 1
    assert "cannot read payload" in result.stderr
    assert "Traceback" not in result.stderr


def test_cli_store_accepts_a_non_ascii_size_under_a_non_utf8_locale(db_conn, tmp_path):
    """read_text() decoded with the locale encoding, so under ISO-8859-1 a
    legitimate "42 ½" became "42 Â½" and failed the size charset check. Where
    the locale is not installed, Python falls back to UTF-8 and this passes
    trivially rather than failing spuriously."""
    import os

    payload = tmp_path / "payload.json"
    payload.write_bytes(json.dumps(
        {"known_good_shoes": [{"brand": "Scarpa", "model": "Drago", "size": "42 ½"}]},
        ensure_ascii=False,
    ).encode("utf-8"))
    env = {**os.environ, "LC_ALL": "en_US.ISO8859-1", "PYTHONUTF8": "0"}
    result = subprocess.run(
        [sys.executable, str(STORE_CLI), str(payload), "--database-url", _database_url(), "--dry-run"],
        capture_output=True, text=True, timeout=30, env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "[dry run, rolled back] survey_token=" in result.stdout
