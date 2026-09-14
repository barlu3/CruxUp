# Local Setup

CruxUp is a climbing shoe recommender: a Python backend (FastAPI, Postgres) and
a Next.js frontend. The plan of record is [`timeline.md`](timeline.md).

Current state: **W0 foundations.** The schema, catalogue, prior model and corpus
collector exist. The API and frontend are still stubs.

---

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | 3.10+ | Needs `X \| None` syntax and `datetime.fromisoformat` |
| PostgreSQL | 14+ | 16 is what the migration is verified against |
| Node | 18+ | Frontend only; not needed for backend work |

---

## 1. Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
```

Three packages are used by tooling but deliberately not in `requirements.txt`,
because they are dev-time only:

```bash
pip install pytest numpy pglast
```

- `numpy` — refitting the prior model (`priors.py --refit`). `derive_prior()`
  itself is pure Python and does not need it.
- `pglast` — validates the DDL against the real PostgreSQL grammar without a
  running server.

---

## 2. Postgres

### macOS (Homebrew)

```bash
brew install postgresql@16
```

**The `LC_ALL` export is not optional on macOS.** Without it the server dies at
startup with `postmaster became multithreaded during startup`.

```bash
export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH"
export LC_ALL="en_US.UTF-8"

pg_ctl -D /opt/homebrew/var/postgresql@16 -l /tmp/pg16.log start
pg_isready          # expect: accepting connections
```

To stop it:

```bash
pg_ctl -D /opt/homebrew/var/postgresql@16 stop
```

To run it as a login service instead: `brew services start postgresql@16`.

### Linux

```bash
sudo apt install postgresql-16      # or your distro's equivalent
sudo systemctl start postgresql
```

---

## 3. Create and migrate the database

```bash
createdb cruxup
psql -d cruxup -f backend/app/db/migrations/0001_init.sql
```

Verify:

```bash
psql -d cruxup -c "\dt"
# shoe, shoe_alias, shoe_size_map, user_survey, recommendation
```

To roll back:

```bash
psql -d cruxup -f backend/app/db/migrations/0001_init_down.sql
```

The pair is reversible and re-appliable — `init` → `down` → `init` runs clean.

> Only the **product** schema (§8.1) exists. The corpus half (§8.2 —
> `corpus_snapshot`, `mention`, `extraction`, `shoe_axis_score`, `lexicon`) is
> W0-1b and is deliberately deferred until the source question resolves. See
> timeline.md D5.

---

## 4. Environment

```bash
cp .env.example .env
```

`.env` is gitignored. For backend work only `DATABASE_URL` is required:

```
DATABASE_URL=postgresql://localhost/cruxup
```

Everything else is optional and the code degrades cleanly without it:

| Variable | Needed for | Without it |
|---|---|---|
| `YOUTUBE_API_KEY` | Corpus collection | Collector logs `unavailable` and skips |
| `REDDIT_*` | Reddit adapter (W1-0c) | Skipped — **by design**, see D11 |
| `CRUXUP_AUTHOR_SALT` | Author hashing | Falls back to a dev salt |
| `ANTHROPIC_API_KEY` | LLM extraction (W2-2) | Not used yet |

---

## 5. Seed the catalogue

```bash
python3 backend/app/catalog/validate.py        # check before loading
python3 backend/app/catalog/seed.py --dry-run  # exercise the load, roll back
python3 backend/app/catalog/seed.py            # commit
```

Expect `30 inserted, 0 updated, 71 aliases`. Running it again gives
`0 inserted, 30 updated` — it upserts on `(brand, model, version, gender)` and
each shoe keeps its UUID, because `recommendation.shoe_id` points at it.

`seed.py` refuses to run against an invalid catalogue. If validation fails it
prints what is wrong and touches nothing.

---

## 6. Verify

```bash
python3 -m pytest backend/tests/ -q        # 54 tests, no network, no database
python3 backend/app/catalog/validate.py    # catalogue invariants
python3 backend/app/catalog/priors.py      # spec model vs hand placements
```

Validate the DDL without a server:

```bash
python3 -c "
from pglast import parse_sql
for f in ['backend/app/db/migrations/0001_init.sql',
          'backend/app/db/migrations/0001_init_down.sql']:
    print(f, len(parse_sql(open(f).read())), 'statements OK')"
```

---

## 7. Frontend

```bash
npm install
npm run dev        # http://localhost:3000
```

Every page under `src/app/` is currently a stub. Frontend work is W6-1/2/3.

---

## Working on the catalogue

The catalogue is `backend/app/catalog/data/shoes.yaml`. **Run `validate.py`
after every edit** — it enforces the things that have already been got wrong by
hand: the count band, the §3 anchor placements, alias uniqueness, prior ranges,
and enum agreement with the SQL `CHECK` constraints.

Quadrant priors come from three places, and the distinction matters for §7.7
confidence:

| `prior_source` | Meaning | Confidence |
|---|---|---|
| `corpus` | §7.4 aggregation, `N_j >= N_min` | Highest |
| `hand` | Human judgement; the 30-shoe calibration set | Middle |
| `spec` | `priors.py` from manufacturer specs | Lowest |

Adding a shoe needs only the spec fields — `derive_prior()` supplies the
placement, so no judgement call is required:

```python
from priors import derive_prior
x, y = derive_prior({"downturn": "aggressive", "last_shape": "asymmetric",
                     "stiffness_spec": "soft", "closure": "velcro"})
```

If you change any hand placement, refit and paste the weights back:

```bash
python3 backend/app/catalog/priors.py --refit
```

The model currently scores **LOOCV MAE x 0.139 / y 0.113, 87% quadrant
agreement** — better than the ≤0.2 that §9.2 asks of the NLP pipeline.
`test_priors.py` fails if that regresses.

---

## Running the collector

```bash
python3 backend/app/scraping/collector.py            # collect
python3 backend/app/scraping/collector.py --status   # documents per day
```

It lands raw documents in a local SQLite store at
`backend/data/corpus_landing.sqlite3`, **not** in Postgres — normalisation into
the §8.2 `mention` schema is W1-full. Keeping raw means a normalisation bug is
recoverable without re-collecting, which matters because re-collecting is
impossible: Pushshift is dead, so the corpus only accrues forward in wall-clock
time.

Collection is idempotent across restarts, so it is safe to run on a schedule.

**Reddit is unavailable and that is deliberate** (D11). Self-service app
registration is closed; every OAuth client needs manual approval, reported at
2–4 weeks and refusable. The free tier is non-commercial only. YouTube and
climbing forums are the primary corpus; Reddit is an adapter that lights up if
approval ever lands.

---

## Troubleshooting

**`postmaster became multithreaded during startup`** — `LC_ALL` is unset. See §2.

**`error: the shoe table does not exist`** — migration not applied. See §3.

**`catalogue failed validation; refusing to seed`** — working as intended.
`validate.py` prints the specific failure; fix the YAML rather than bypassing
the check.

**`ModuleNotFoundError: No module named 'yaml'`** — virtualenv not active, or
`pip install -r backend/requirements.txt` not run.

**Tests pass but seeding fails** — the suite needs no database by design, so any
database-dependent failure is environment rather than code. Check `DATABASE_URL`
and that Postgres is actually running (`pg_isready`).
