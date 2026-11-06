"""[W6-2] Pins frontend/src/app/lib/types.ts to the Python contract it mirrors:
survey/schema.py, survey/anchors.py, GET /shoes (ShoeOut), GET /quadrant
(QuadrantShoeOut) and POST /recommend (RecommendOut, W6-3).

The TypeScript string-literal unions and interface keys are parsed back out of
the source text, the way test_survey.py parses the CHECK constraints out of
0001_init.sql, so a hand-edit on either side fails here instead of surfacing
as a 422 or a rejected response at runtime.
"""

from __future__ import annotations

import re
import sys
import typing
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
TYPES_TS = BACKEND.parent / "frontend" / "src" / "app" / "lib" / "types.ts"

sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "app" / "survey"))
# `import priors` below runs before quadrant.py gets to put the catalog dir
# on sys.path itself, so it is added here; index 2 mirrors test_api.py.
sys.path.insert(2, str(BACKEND / "app" / "catalog"))
import anchors as A  # noqa: E402
import priors as PR  # noqa: E402
import schema as S   # noqa: E402
from app.api.routes.quadrant import QuadrantShoeOut  # noqa: E402
from app.api.routes.recommend import (  # noqa: E402
    GatedOutOut,
    RecommendationOut,
    RecommendOut,
    TargetOut,
    TermsOut,
)
from app.api.routes.shoes import ShoeOut  # noqa: E402

# store.build_survey_row derives these from `goal` and refuses them from a client.
CLIENT_REFUSED_FIELDS = {"goal_x_target", "goal_y_target"}

TS_UNION_FOR_ENUM = {
    "foot_width": "FootWidth",
    "instep": "Instep",
    "toe_shape": "ToeShape",
    "arch": "Arch",
    "heel_fit": "HeelFit",
    "discipline": "Discipline",
    "terrain": "Terrain",
    "level": "Level",
}
PYTHON_ENUMS = {**S.ENUMS, **S.PY_ONLY_ENUMS}


def _strip_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", source)


def _parse_union(source: str, name: str) -> list[str]:
    match = re.search(rf"export type {name}\s*=\s*([^;]*);", _strip_comments(source))
    assert match, f'types.ts has no `export type {name} = "..." | ...;`'
    return re.findall(r"""["']([^"']*)["']""", match.group(1))


def _parse_interface_keys(source: str, name: str) -> list[str]:
    match = re.search(
        rf"export interface {name}(?:\s+extends\s+\w+)?\s*\{{([^}}]*)\}}",
        _strip_comments(source),
    )
    assert match, f"types.ts has no `export interface {name} {{...}}`"
    return re.findall(r"^\s*(\w+)\??\s*:", match.group(1), flags=re.MULTILINE)


@pytest.fixture(scope="module")
def types_source() -> str:
    return TYPES_TS.read_text()


def test_every_python_enum_has_a_typescript_union_mapping():
    assert set(TS_UNION_FOR_ENUM) == set(PYTHON_ENUMS)


@pytest.mark.parametrize("field", sorted(TS_UNION_FOR_ENUM))
def test_typescript_enum_union_matches_python_without_duplicates(field, types_source):
    parsed = _parse_union(types_source, TS_UNION_FOR_ENUM[field])
    assert sorted(parsed) == sorted(PYTHON_ENUMS[field])


def test_typescript_gender_matches_anchor_genders(types_source):
    assert sorted(_parse_union(types_source, "Gender")) == sorted(A.GENDERS)


def test_typescript_survey_payload_keys_are_allowed_keys_minus_derived_targets(types_source):
    """`goal` is accepted by store.build_survey_row but deliberately absent:
    the questionnaire does not ask it yet (SurveyForm.tsx)."""
    parsed = _parse_interface_keys(types_source, "SurveyPayload")
    assert sorted(parsed) == sorted(S.ALLOWED_KEYS - CLIENT_REFUSED_FIELDS)


def test_typescript_anchor_entry_keys_match_anchor_allowed_keys(types_source):
    parsed = _parse_interface_keys(types_source, "AnchorEntry")
    assert sorted(parsed) == sorted(A.ANCHOR_ALLOWED_KEYS)


def test_typescript_shoe_keys_match_shoe_out_fields(types_source):
    parsed = _parse_interface_keys(types_source, "Shoe")
    assert sorted(parsed) == sorted(ShoeOut.model_fields)


def test_typescript_prior_source_matches_python_prior_source_values(types_source):
    parsed = _parse_union(types_source, "PriorSource")
    assert sorted(parsed) == sorted(s.value for s in PR.PriorSource)


def test_typescript_quadrant_matches_quadrant_shoe_out_literal(types_source):
    expected = typing.get_args(QuadrantShoeOut.model_fields["quadrant"].annotation)
    assert sorted(_parse_union(types_source, "Quadrant")) == sorted(expected)


def test_typescript_quadrant_shoe_keys_match_quadrant_shoe_out_fields(types_source):
    parsed = _parse_interface_keys(types_source, "QuadrantShoe")
    assert sorted(parsed) == sorted(QuadrantShoeOut.model_fields)


def test_typescript_confidence_label_matches_recommendation_literal(types_source):
    expected = typing.get_args(RecommendationOut.model_fields["confidence_label"].annotation)
    assert sorted(_parse_union(types_source, "ConfidenceLabel")) == sorted(expected)


def test_typescript_recommendation_extends_quadrant_shoe(types_source):
    assert re.search(
        r"export interface Recommendation extends QuadrantShoe\s*\{", _strip_comments(types_source)
    )


def test_typescript_recommendation_keys_are_the_fields_added_to_quadrant_shoe_out(types_source):
    parsed = _parse_interface_keys(types_source, "Recommendation")
    assert sorted(parsed) == sorted(
        set(RecommendationOut.model_fields) - set(QuadrantShoeOut.model_fields)
    )


@pytest.mark.parametrize(
    ("interface", "model"),
    [
        ("RecommendResponse", RecommendOut),
        ("RecommendTarget", TargetOut),
        ("RecommendTerms", TermsOut),
        ("GatedOut", GatedOutOut),
    ],
)
def test_typescript_recommend_interface_keys_match_pydantic_fields(interface, model, types_source):
    assert sorted(_parse_interface_keys(types_source, interface)) == sorted(model.model_fields)


def test_parser_fails_loudly_when_a_union_is_missing(types_source):
    with pytest.raises(AssertionError, match="NoSuchType"):
        _parse_union(types_source, "NoSuchType")


def test_parser_ignores_commented_out_values():
    source = 'export type X =\n  | "a" // | "b"\n  /* | "c" */;'
    assert _parse_union(source, "X") == ["a"]


def test_interface_parser_reads_optional_keys_and_skips_doc_comments():
    source = 'export interface Y {\n  /** a: doc */\n  a?: string;\n  b: number;\n}'
    assert _parse_interface_keys(source, "Y") == ["a", "b"]


def test_interface_parser_reads_keys_of_an_extending_interface():
    source = "export interface Child extends Base {\n  a: string;\n  b?: number;\n}"
    assert _parse_interface_keys(source, "Child") == ["a", "b"]
