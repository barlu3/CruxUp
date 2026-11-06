"""[W6-2] GET /quadrant -- every shoe with a quadrant prior, for the
frontend's quadrant view. A separate router from routes/shoes.py on purpose:
GET /shoes is the anchor picker's identity listing and its docstring pins
identity columns only, so the priors live here instead of widening it.

Only shoes with a prior are listed (`quadrant_x_prior IS NOT NULL`). The
paired CHECKs shoe_prior_paired and shoe_prior_source_paired in
0001_init.sql guarantee that `quadrant_y_prior` and `prior_source` are set
whenever `quadrant_x_prior` is, so filtering on x alone is enough and the
three fields below are never None.

`is_anchor` is not a column: seed.py drops the yaml `anchor` flag, so the
canonical section-3 anchor set is `validate.ANCHORS`, imported as the FLAT
`validate` module exactly as seed.py does (stdlib + yaml only), with
`priors` alongside it. Caveat: the ANCHORS key is (brand, model, version)
with no gender, so if a gendered twin of an anchor were ever added, both
rows would be flagged. No such row exists today.

`quadrant` comes from `priors.quadrant`, which answers "ON-AXIS" for a prior
on an axis. That is outside this response's Literal, so response validation
fails and main.py's catch-all returns the masked 500. The failure is
intended and loud: validate.py treats an on-axis prior as a catalogue bug,
and serving it quietly would hide that.

Priors arrive from psycopg as Decimal (the columns are NUMERIC(4,3)); they
are converted to float so they serialise as JSON numbers.

Plain `def`, not `async def` -- same reasoning as routes/survey.py: psycopg
is synchronous and FastAPI runs sync handlers in its own threadpool.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

import psycopg
from fastapi import APIRouter, Depends
from pydantic import BaseModel

# Flat sibling imports of the catalog package's own directory, the same
# pattern seed.py uses for itself; see deps.py's module docstring.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "catalog"))
import priors  # noqa: E402
from validate import ANCHORS  # noqa: E402

from app.api.deps import get_conn

router = APIRouter()


class QuadrantShoeOut(BaseModel):
    id: str
    brand: str
    model: str
    version: str
    gender: str
    x: float
    y: float
    prior_source: Literal["corpus", "hand", "spec"]
    is_anchor: bool
    quadrant: Literal["Q1", "Q2", "Q3", "Q4"]


def list_quadrant(conn: psycopg.Connection) -> list[dict[str, str | float | bool]]:
    """Every shoe with a prior, ordered for a stable listing. The query takes
    no bind parameters; `conn` is only the connection to run it on. The
    trailing `brand, model, id` make the order total (case-variant names
    and equal keys would otherwise tie)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, brand, model, version, gender, "
            "quadrant_x_prior, quadrant_y_prior, prior_source "
            "FROM shoe WHERE quadrant_x_prior IS NOT NULL "
            "ORDER BY lower(brand), lower(model), version, gender, brand, model, id"
        )
        items = []
        for row in cur.fetchall():
            x, y = float(row[5]), float(row[6])
            items.append(
                {
                    "id": str(row[0]),
                    "brand": row[1],
                    "model": row[2],
                    "version": row[3],
                    "gender": row[4],
                    "x": x,
                    "y": y,
                    "prior_source": row[7],
                    "is_anchor": (row[1], row[2], row[3]) in ANCHORS,
                    "quadrant": priors.quadrant(x, y),
                }
            )
        return items


@router.get("/quadrant", response_model=list[QuadrantShoeOut])
def get_quadrant(
    conn: psycopg.Connection = Depends(get_conn),
) -> list[dict[str, str | float | bool]]:
    return list_quadrant(conn)
