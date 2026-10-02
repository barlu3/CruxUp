"""[W7-1] GET /shoes -- backs the frontend's anchor picker.

Exposes `version` (and `gender`) because three real catalog rows share
(brand, model) and differ only by one or both of those fields (see
survey/anchors.py's own module docstring, which names them as the exact
reason resolution there is a hard ambiguity error rather than a guess):

    Scarpa Instinct        -> VS, VSR
    La Sportiva Katana     -> Lace, Velcro
    La Sportiva Solution   -> '' (base), Comp

Without `version`/`gender` in this response, a picker built on it could not
tell those rows apart -- exactly the ambiguity anchors.py refuses to guess
at. (See backend/tests/test_api.py's round-trip property, section C: every
item this endpoint returns must resolve, unambiguously, back through
`anchors._resolve_one` to itself.)

No `status` filter: `anchors.PostgresCatalog.by_identity` resolves an anchor
against a shoe row of ANY status, so every shoe the server can resolve as an
anchor must be pickable here too -- a discontinued shoe a climber owned is a
legitimate anchor, not something to hide from the picker.

No pagination: the catalog is ~30 rows today, growing to ~100 once D12 lands;
autocomplete filters this list client-side.

Plain `def`, not `async def` -- same reasoning as routes/survey.py: psycopg
is synchronous and FastAPI runs sync handlers in its own threadpool.
"""

from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_conn

router = APIRouter()


class ShoeOut(BaseModel):
    """Exactly the columns in shoe_unique_identity (0001_init.sql) plus the
    id -- nothing else from `shoe` is exposed here."""

    id: str
    brand: str
    model: str
    version: str
    gender: str


def list_shoes(conn: psycopg.Connection) -> list[dict[str, str]]:
    """Every `shoe` row, no `status` filter, no pagination -- see the module
    docstring. The query itself takes no bind parameters (it is an
    unconditional SELECT); `conn` is only the connection to run it on.
    Ordered for a stable, predictable picker listing."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, brand, model, version, gender FROM shoe "
            "ORDER BY lower(brand), lower(model), version, gender"
        )
        return [
            {
                "id": str(row[0]),
                "brand": row[1],
                "model": row[2],
                "version": row[3],
                "gender": row[4],
            }
            for row in cur.fetchall()
        ]


@router.get("/shoes", response_model=list[ShoeOut])
def get_shoes(conn: psycopg.Connection = Depends(get_conn)):
    return list_shoes(conn)
