"""[W5-1] Derive quadrant priors from manufacturer spec fields.

Why this exists
---------------
D6 originally cut the catalogue from 50-100 shoes to 30, on the argument that
only ~15-25 shoes will ever clear N_min so the rest would be "an NLP veneer
over a spec sheet". That argument was wrong, and D6 has been revised.

It conflated two independent things: how many shoes have *corpus signal*, and
how many shoes the catalogue *contains*. Fit (section 7.2) and Budget
(section 7.6) do not touch the corpus at all, so trimming the catalogue
degraded them for no NLP-related reason. Measured on the 30-shoe catalogue, a
typical user saw 3-4 candidates after the size and budget gates, and a user
with an uncommon size or tight budget saw fewer than two.

The genuine constraint was never the corpus -- it was that hand-placing each
shoe needs a *judgement call*, and judgement does not scale to 100 shoes.

This module removes that bottleneck. Spec fields predict hand placements well
enough that adding shoe 31..100 costs a spec lookup rather than a judgement:

    LOOCV (held out, n=30):  MAE x = 0.139   MAE y = 0.113
    quadrant agreement:      26/30 = 87%

For scale, section 9.2 sets MAE <= 0.2 as the pass threshold for the *NLP
pipeline*. A linear model over four spec fields already beats it.

Evaluation is leave-one-out, not an 80/20 split, for the same reason D8 gives:
at n=30 a holdout leaves too few test points to mean anything.

Provenance, not just numbers
----------------------------
Every prior carries a PriorSource. A hand-placed prior is a human judgement; a
spec-derived one is this model's output; a corpus-derived one comes from
section 7.4 aggregation once N_j >= N_min. They are NOT interchangeable, and
section 7.7 confidence must reflect which one produced a placement.

Reproducibility
---------------
WEIGHTS below were produced by refit() against the hand-placed catalogue. They
are checked in so behaviour is deterministic, but they are not magic numbers --
`python3 backend/app/catalog/priors.py --refit` regenerates them and prints the
LOOCV score. Re-run it whenever hand placements change.
"""

from __future__ import annotations

import argparse
import enum
import sys
from pathlib import Path

import yaml


class PriorSource(str, enum.Enum):
    """Where a quadrant placement came from. Feeds section 7.7 confidence."""

    CORPUS = "corpus"  # section 7.4 aggregation, N_j >= N_min -- best
    HAND = "hand"      # human judgement; the calibration set
    SPEC = "spec"      # this model -- broad coverage, lower confidence


# Feature vocabulary. Order matters: WEIGHTS is indexed against it.
DOWNTURN = ("flat", "moderate", "aggressive")
LAST = ("neutral", "semi-asymmetric", "asymmetric")
STIFFNESS = ("very soft", "soft", "moderate-soft", "moderate", "moderate-stiff", "stiff")
CLOSURE = ("slipper", "velcro", "lace")

FEATURE_NAMES = (
    ["bias"]
    + [f"downturn={v}" for v in DOWNTURN]
    + [f"last={v}" for v in LAST]
    + [f"stiffness={v}" for v in STIFFNESS]
    + [f"closure={v}" for v in CLOSURE]
    + ["flat_and_stiff", "soft_slipper"]
)

# Fitted against the 30 hand-placed shoes. See --refit.
#
# The two interaction terms are the point of this model. `flat_and_stiff`
# carries w_x = +0.322: a flat last alone reads as comfort, but flat AND stiff
# is a precision edging shoe (Katana Lace, Anasazi Pro), which is performance.
# Without it the naive lookup put those shoes in the wrong half of the plane.
WEIGHTS: dict[str, tuple[float, ...]] = {
    "x": (
        +0.040,                                            # bias
        -0.110, +0.031, +0.118,                            # downturn
        -0.610, +0.097, +0.553,                            # last_shape
        +0.113, -0.004, -0.043, +0.056, -0.129, +0.046,    # stiffness
        +0.133, -0.024, -0.069,                            # closure
        +0.322,                                            # flat_and_stiff
        +0.133,                                            # soft_slipper
    ),
    "y": (
        +0.009,
        +0.164, -0.141, -0.013,
        -0.114, -0.063, +0.186,
        +0.643, +0.312, +0.207, -0.130, -0.432, -0.591,
        -0.001, +0.025, -0.015,
        -0.087,
        -0.001,
    ),
}

# LOOCV score of the checked-in weights. Asserted by the test suite so a
# silent regression in the feature set or the catalogue is caught.
LOOCV_MAE_X = 0.139
LOOCV_MAE_Y = 0.113
LOOCV_AGREEMENT = 26 / 30


def _vector(shoe: dict) -> list[float]:
    """One-hot feature vector, in FEATURE_NAMES order."""
    downturn = shoe.get("downturn")
    last = shoe.get("last_shape")
    stiff = shoe.get("stiffness_spec")
    closure = shoe.get("closure")

    vec = [1.0]
    vec += [1.0 if downturn == v else 0.0 for v in DOWNTURN]
    vec += [1.0 if last == v else 0.0 for v in LAST]
    vec += [1.0 if stiff == v else 0.0 for v in STIFFNESS]
    vec += [1.0 if closure == v else 0.0 for v in CLOSURE]
    vec.append(1.0 if (downturn == "flat" and stiff in ("stiff", "moderate-stiff")) else 0.0)
    vec.append(1.0 if (closure == "slipper" and stiff in ("very soft", "soft")) else 0.0)
    return vec


def derive_prior(shoe: dict) -> tuple[float, float]:
    """Predict (x, y) from spec fields. Always returns a point on the plane.

    Clamped to [-1,1] to satisfy the shoe_prior_x_range / shoe_prior_y_range
    CHECK constraints, and nudged off zero: a prior sitting exactly on an axis
    has no quadrant, which validate.py rejects.
    """
    vec = _vector(shoe)
    x = sum(v * w for v, w in zip(vec, WEIGHTS["x"]))
    y = sum(v * w for v, w in zip(vec, WEIGHTS["y"]))
    x = max(-1.0, min(1.0, x))
    y = max(-1.0, min(1.0, y))
    # Exact zero is unplaceable; push to the comfort/stiff side, the
    # conservative direction for a shoe we know little about.
    if x == 0.0:
        x = -0.001
    if y == 0.0:
        y = -0.001
    return round(x, 3), round(y, 3)


def quadrant(x: float, y: float) -> str:
    if x > 0 and y < 0: return "Q1"
    if x < 0 and y < 0: return "Q2"
    if x < 0 and y > 0: return "Q3"
    if x > 0 and y > 0: return "Q4"
    return "ON-AXIS"


# ---------------------------------------------------------------------------
# Refitting (dev-time only; needs numpy, which derive_prior does not)
# ---------------------------------------------------------------------------

def refit(shoes: list[dict]) -> dict:
    """Refit weights against hand-placed shoes and score under LOOCV."""
    import numpy as np

    X = np.array([_vector(s) for s in shoes])
    yx = np.array([s["quadrant_x_prior"] for s in shoes], dtype=float)
    yy = np.array([s["quadrant_y_prior"] for s in shoes], dtype=float)

    errs_x, errs_y, agree = [], [], 0
    for i in range(len(shoes)):
        mask = np.ones(len(shoes), dtype=bool)
        mask[i] = False
        wx = np.linalg.lstsq(X[mask], yx[mask], rcond=None)[0]
        wy = np.linalg.lstsq(X[mask], yy[mask], rcond=None)[0]
        px = float(np.clip(X[i] @ wx, -1, 1))
        py = float(np.clip(X[i] @ wy, -1, 1))
        errs_x.append(abs(px - yx[i]))
        errs_y.append(abs(py - yy[i]))
        agree += quadrant(px, py) == quadrant(yx[i], yy[i])

    return {
        "x": tuple(round(float(w), 3) for w in np.linalg.lstsq(X, yx, rcond=None)[0]),
        "y": tuple(round(float(w), 3) for w in np.linalg.lstsq(X, yy, rcond=None)[0]),
        "mae_x": float(np.mean(errs_x)),
        "mae_y": float(np.mean(errs_y)),
        "agreement": agree / len(shoes),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Spec-derived quadrant priors (W5-1)")
    ap.add_argument("--refit", action="store_true",
                    help="refit weights against hand-placed shoes and print them")
    ap.add_argument("--catalog", type=Path,
                    default=Path(__file__).resolve().parent / "data" / "shoes.yaml")
    args = ap.parse_args()

    shoes = (yaml.safe_load(args.catalog.read_text()) or {})["shoes"]

    if args.refit:
        hand = [s for s in shoes
                if s.get("quadrant_x_prior") is not None
                and s.get("prior_source", "hand") == "hand"]
        if len(hand) < 20:
            print(f"error: only {len(hand)} hand-placed shoes; too few to refit",
                  file=sys.stderr)
            return 1
        r = refit(hand)
        print(f"fitted on {len(hand)} hand-placed shoes")
        print(f"LOOCV  MAE x = {r['mae_x']:.3f}  MAE y = {r['mae_y']:.3f}  "
              f"agreement = {r['agreement']*100:.0f}%")
        print("(section 9.2 NLP threshold is MAE <= 0.2)")
        print("\nPaste into WEIGHTS:")
        for axis in ("x", "y"):
            print(f'    "{axis}": (' + ", ".join(f"{w:+.3f}" for w in r[axis]) + "),")
        return 0

    # Default: report how the checked-in model scores against hand placements.
    print(f"{'shoe':34s} {'hand':>14s} {'spec':>14s}   quad")
    print("-" * 78)
    mism = 0
    for s in sorted(shoes, key=lambda s: (s["brand"], s["model"])):
        hx, hy = s.get("quadrant_x_prior"), s.get("quadrant_y_prior")
        px, py = derive_prior(s)
        name = f"{s['brand']} {s['model']} {s.get('version','')}".strip()
        hq, pq = quadrant(hx, hy), quadrant(px, py)
        if hq != pq:
            mism += 1
        flag = "" if hq == pq else "  <- differs"
        print(f"{name:34s} ({hx:+.2f},{hy:+.2f}) ({px:+.2f},{py:+.2f})   {hq}/{pq}{flag}")
    print(f"\n{len(shoes)-mism}/{len(shoes)} agree on quadrant")
    return 0


if __name__ == "__main__":
    sys.exit(main())
