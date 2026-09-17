"""[W5-1] Catalog validation.

Exists because the seed catalogue was hand-written and the hand-written
annotations were wrong three times on the first pass: the header claimed 28
shoes when there were 31, the per-quadrant counts were wrong, and one shoe was
filed under a quadrant heading its own priors contradict. Those are exactly the
errors a machine catches for free.

Run after any edit to shoes.yaml:

    python3 backend/app/catalog/validate.py

Before the budget gate ships (section 7.6), run with --require-msrp. That flips
the null-price warning into a hard failure, which is the guard that stops a
catalogue full of null prices reaching a user-facing budget filter.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import yaml

CATALOG = Path(__file__).resolve().parent / "data" / "shoes.yaml"

# D6: rescoped from 50-100 to a deliberately small, mostly corpus-backed set.
MIN_SHOES, MAX_SHOES = 25, 30

# timeline.md section 3, CORRECTED placements. The v2 table had four of these
# five inverted, and they are calibration ground truth, so they are asserted
# here rather than trusted to a comment.
ANCHORS = {
    ("La Sportiva", "Solution", ""):  "Q1",
    ("La Sportiva", "TC Pro", ""):    "Q2",
    ("Evolv", "Defy", ""):            "Q3",
    ("Scarpa", "Drago", ""):          "Q4",
    ("Scarpa", "Instinct", "VSR"):    "Q4",
}

# Mirrors the CHECK constraints in 0001_init.sql. If these drift apart, the
# seed load fails at the database instead of here, which is a worse place.
ENUMS = {
    "gender":   {"mens", "womens", "unisex"},
    "downturn": {"flat", "moderate", "aggressive"},
    "closure":  {"lace", "velcro", "slipper"},
}

# Mirrors shoe_prior_source_valid, and priors.PriorSource.
PRIOR_SOURCES = {"corpus", "hand", "spec"}


def quadrant(x: float, y: float) -> str:
    if x > 0 and y < 0: return "Q1"
    if x < 0 and y < 0: return "Q2"
    if x < 0 and y > 0: return "Q3"
    if x > 0 and y > 0: return "Q4"
    return "ON-AXIS"


def validate(path: Path = CATALOG, require_msrp: bool = False) -> list[str]:
    """Return a list of error strings. Empty means the catalogue is sound."""
    errors: list[str] = []

    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        return [f"YAML does not parse: {exc}"]

    # Structure first. Everything below assumes a mapping root, a list of
    # shoes, and a mapping per shoe; hand-edited YAML violates all three
    # easily, and each would otherwise surface as an AttributeError or
    # TypeError crash rather than a readable validation error.
    if not isinstance(data, dict):
        return [f"catalogue root must be a mapping with a 'shoes' key, got {type(data).__name__}"]
    shoes = data.get("shoes")
    if not isinstance(shoes, list):
        return [f"'shoes' must be a list, got {type(shoes).__name__}"]
    if not shoes:
        return ["no shoes found under top-level key 'shoes'"]
    malformed = [i for i, s in enumerate(shoes) if not isinstance(s, dict)]
    if malformed:
        return [f"shoes[{i}] must be a mapping, got {type(shoes[i]).__name__}" for i in malformed]

    # --- D6 count band ------------------------------------------------------
    if not MIN_SHOES <= len(shoes) <= MAX_SHOES:
        errors.append(
            f"count {len(shoes)} outside the D6 band {MIN_SHOES}-{MAX_SHOES}. "
            f"Trim rows, or amend D6 in timeline.md if the band has moved."
        )

    seen_aliases: dict[str, str] = {}
    seen_identity: set[tuple] = set()
    quad_counts: Counter = Counter()
    missing_msrp: list[str] = []

    for i, s in enumerate(shoes):
        label = f"{s.get('brand','?')} {s.get('model','?')} {s.get('version','')}".strip()

        # Field types. A non-string identity field is unhashable in the
        # identity set; a string prior ("0.5") raises TypeError in the range
        # comparison; a non-list `aliases` breaks iteration. Report and skip
        # the rest of this entry rather than crash.
        type_errors = []
        for field in ("brand", "model", "gender", "version"):
            if s.get(field) is not None and not isinstance(s[field], str):
                type_errors.append(f"{field} must be a string")
        for field in ("quadrant_x_prior", "quadrant_y_prior", "msrp_usd"):
            v = s.get(field)
            if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float))):
                type_errors.append(f"{field} must be a number, got {type(v).__name__}")
        aliases_raw = s.get("aliases")
        if aliases_raw is not None and (
            not isinstance(aliases_raw, list) or not all(isinstance(a, str) for a in aliases_raw)
        ):
            type_errors.append("aliases must be a list of strings")
        if type_errors:
            errors.extend(f"shoes[{i}] ({label}): {e}" for e in type_errors)
            continue

        # --- prior provenance (mirrors shoe_prior_source_valid / _paired) ---
        source = s.get("prior_source")
        has_prior = s.get("quadrant_x_prior") is not None
        if source is not None and source not in PRIOR_SOURCES:
            errors.append(f"{label}: prior_source='{source}' not in {sorted(PRIOR_SOURCES)}")
        if has_prior and source is None:
            errors.append(
                f"{label}: has a quadrant prior but no prior_source; section 7.7 "
                f"confidence cannot tell a hand placement from a spec guess"
            )
        if source is not None and not has_prior:
            errors.append(f"{label}: prior_source set without a placement")

        for required in ("brand", "model", "gender", "quadrant_x_prior", "quadrant_y_prior"):
            if s.get(required) is None:
                errors.append(f"{label}: missing required field '{required}'")

        # --- enums must match the SQL CHECK constraints ---------------------
        for field, allowed in ENUMS.items():
            val = s.get(field)
            if val is not None and val not in allowed:
                errors.append(f"{label}: {field}='{val}' not in {sorted(allowed)}")

        # --- priors ---------------------------------------------------------
        x, y = s.get("quadrant_x_prior"), s.get("quadrant_y_prior")
        if x is not None and y is not None:
            if not (-1 <= x <= 1):
                errors.append(f"{label}: quadrant_x_prior {x} outside [-1,1]")
            if not (-1 <= y <= 1):
                errors.append(f"{label}: quadrant_y_prior {y} outside [-1,1]")
            q = quadrant(x, y)
            quad_counts[q] += 1
            if q == "ON-AXIS":
                errors.append(
                    f"{label}: prior ({x},{y}) sits exactly on an axis, so it has "
                    f"no quadrant. Nudge it off zero and say which side it belongs."
                )
            # --- anchors ----------------------------------------------------
            key = (s.get("brand"), s.get("model"), s.get("version", "") or "")
            if key in ANCHORS:
                if not s.get("anchor"):
                    errors.append(f"{label}: is a section-3 anchor but lacks `anchor: true`")
                if q != ANCHORS[key]:
                    errors.append(
                        f"{label}: ANCHOR REGRESSION - priors put it in {q}, "
                        f"section 3 says {ANCHORS[key]}. This is calibration ground "
                        f"truth; do not 'fix' it by changing section 3."
                    )
        elif (x is None) != (y is None):
            errors.append(f"{label}: one prior set without the other; they are a pair")

        # --- identity (mirrors shoe_unique_identity) ------------------------
        identity = (s.get("brand"), s.get("model"), s.get("version", "") or "", s.get("gender"))
        if identity in seen_identity:
            errors.append(f"{label}: duplicate (brand, model, version, gender)")
        seen_identity.add(identity)

        # --- aliases (mirrors shoe_alias_globally_unique) -------------------
        aliases = s.get("aliases") or []
        if not aliases:
            errors.append(f"{label}: no aliases; mention detection (W1-3) needs at least one")
        for alias in aliases:
            k = alias.lower()
            if k in seen_aliases:
                errors.append(
                    f"alias '{alias}' claimed by both {seen_aliases[k]} and {label}. "
                    f"Ambiguous aliases are a data error, not a runtime branch."
                )
            seen_aliases[k] = label

        if s.get("msrp_usd") is None:
            missing_msrp.append(label)

    # --- MSRP: the section 7.6 budget-gate guard ----------------------------
    if missing_msrp:
        msg = (
            f"{len(missing_msrp)}/{len(shoes)} shoes have msrp_usd = null. "
            f"The budget gate must not treat an unknown price as within budget."
        )
        if require_msrp:
            errors.append("BUDGET GATE BLOCKED: " + msg)
        else:
            print(f"WARNING: {msg}")
            print("         (run with --require-msrp before shipping the budget gate)")

    # --- report -------------------------------------------------------------
    print(f"\n{len(shoes)} shoes, {len(seen_aliases)} unique aliases")
    print("quadrants: " + "  ".join(f"{q} {quad_counts[q]}" for q in ("Q1", "Q2", "Q3", "Q4")))
    thin = [q for q in ("Q1", "Q2", "Q3", "Q4") if quad_counts[q] < 4]
    if thin:
        print(f"note: {', '.join(thin)} thin (<4) - section 9.2 agreement will be noisy there")

    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate the seed catalogue (W5-1)")
    ap.add_argument("--catalog", type=Path, default=CATALOG)
    ap.add_argument(
        "--require-msrp", action="store_true",
        help="fail if any shoe lacks msrp_usd; use before shipping the budget gate",
    )
    args = ap.parse_args()

    errors = validate(args.catalog, require_msrp=args.require_msrp)
    if errors:
        print(f"\n{len(errors)} ERROR(S):")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("\ncatalogue valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
