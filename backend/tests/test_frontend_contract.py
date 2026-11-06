"""[W6-1-B] Pins frontend/src/app/lib/types.ts to the Python survey contract.

The TypeScript `as const` arrays are parsed back out of the source text, the
way test_survey.py parses the CHECK constraints out of 0001_init.sql, so a
hand-edit on either side fails here instead of surfacing as a 400 at runtime.
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

CLIENT_REFUSED_FIELDS = {"goal_x_target", "goal_y_target"}

TS_ARRAY_FOR_ENUM = {
    "foot_width": "FOOT_WIDTHS",
    "instep": "INSTEPS",
    "toe_shape": "TOE_SHAPES",
    "arch": "ARCHES",
    "heel_fit": "HEEL_FITS",
    "discipline": "DISCIPLINES",
    "terrain": "TERRAINS",
    "level": "LEVELS",
}
PYTHON_ENUMS = {**S.ENUMS, **S.PY_ONLY_ENUMS}


def _strip_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", source)


def _parse_const_array(source: str, name: str) -> list[str]:
    pattern = rf"export const {name}\s*=\s*\[([^\]]*)\]\s*as const"
    match = re.search(pattern, _strip_comments(source))
    assert match, f"types.ts has no `export const {name} = [...] as const`"
    return re.findall(r"""["']([^"']*)["']""", match.group(1))


def _parse_interface_keys(source: str, name: str) -> list[str]:
    match = re.search(rf"export interface {name}\s*\{{([^}}]*)\}}", _strip_comments(source))
    assert match, f"types.ts has no `export interface {name} {{...}}`"
    return re.findall(r"^\s*(\w+)\??\s*:", match.group(1), flags=re.MULTILINE)


@pytest.fixture(scope="module")
def types_source() -> str:
    return TYPES_TS.read_text()


def test_every_python_enum_has_a_typescript_array_mapping():
    assert set(TS_ARRAY_FOR_ENUM) == set(PYTHON_ENUMS)


@pytest.mark.parametrize("field", sorted(TS_ARRAY_FOR_ENUM))
def test_typescript_enum_array_matches_python_without_duplicates(field, types_source):
    parsed = _parse_const_array(types_source, TS_ARRAY_FOR_ENUM[field])
    assert sorted(parsed) == sorted(PYTHON_ENUMS[field])


def test_typescript_genders_match_anchor_genders(types_source):
    parsed = _parse_const_array(types_source, "GENDERS")
    assert sorted(parsed) == sorted(A.GENDERS)


def test_typescript_survey_fields_are_allowed_keys_with_raw_goal(types_source):
    expected = (S.ALLOWED_KEYS - CLIENT_REFUSED_FIELDS) | {"goal"}
    parsed = _parse_const_array(types_source, "SURVEY_FIELDS")
    assert sorted(parsed) == sorted(expected)


def test_typescript_anchor_entry_keys_match_anchor_allowed_keys(types_source):
    parsed = _parse_interface_keys(types_source, "AnchorEntry")
    assert sorted(parsed) == sorted(A.ANCHOR_ALLOWED_KEYS)


def test_typescript_prior_sources_match_python_prior_source_values(types_source):
    parsed = _parse_const_array(types_source, "PRIOR_SOURCES")
    assert sorted(parsed) == sorted(s.value for s in PR.PriorSource)


def test_typescript_quadrants_match_quadrant_shoe_out_literal(types_source):
    parsed = _parse_const_array(types_source, "QUADRANTS")
    expected = typing.get_args(QuadrantShoeOut.model_fields["quadrant"].annotation)
    assert sorted(parsed) == sorted(expected)


def test_typescript_quadrant_shoe_keys_match_quadrant_shoe_out_fields(types_source):
    parsed = _parse_interface_keys(types_source, "QuadrantShoe")
    assert sorted(parsed) == sorted(QuadrantShoeOut.model_fields)


def test_parser_fails_loudly_when_an_array_is_missing(types_source):
    with pytest.raises(AssertionError, match="NO_SUCH_ARRAY"):
        _parse_const_array(types_source, "NO_SUCH_ARRAY")


def test_parser_ignores_commented_out_values():
    source = 'export const X = [\n  "a", // "b"\n  /* "c" */\n] as const satisfies readonly string[];'
    assert _parse_const_array(source, "X") == ["a"]
