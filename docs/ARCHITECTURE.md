# CruxUp — Architecture

A reference for the structure, data model and design of the CruxUp climbing shoe recommender. It describes the software **as implemented** and marks where the planned design has not been built yet.

- **Last verified against the codebase:** 2026-11-06
- **Plan, tasks and decisions of record:** [`timeline.md`](../timeline.md). Decision IDs (D1–D12) and task IDs (W0-1a, …) below refer to it.
- **Local setup:** [`SETUP.md`](../SETUP.md)
- **Verification:** the commands at the foot of this document re-check the claims that can be checked mechanically.

---

## 1. System overview

- **Purpose:** recommend climbing shoes on three independent dimensions:
  - **Fit** — does the shoe suit the user's foot? (questionnaire + anchor shoes)
  - **Style** — does the shoe's character match the user's discipline and preferences? (a 2-D quadrant)
  - **Budget** — is it within the user's price limit?
- **The quadrant plane** is the core abstraction. Every shoe and every user target is a point in `[-1,1]²`:
  - `x`: comfort (−1) ↔ performance (+1)
  - `y`: stiff (−1) ↔ soft (+1)
  - Q1 performance+stiff · Q2 comfort+stiff · Q3 comfort+soft · Q4 performance+soft
- **Placement provenance.** A shoe's position has one of three sources, ranked by confidence: **corpus** (aggregated community discussion) > **hand** (human judgement) > **spec** (derived from manufacturer specifications). The source is stored with every placement.
- **Build state:**
  - **Implemented:** the product database schema, the shoe catalogue and its validator, a spec-to-placement model, the catalogue loader, environment configuration, a source-agnostic corpus collector, survey capture (§4.7), preference→target (`q*`) derivation (§4.8), an HTTP API with `POST /survey`, `GET /shoes`, `GET /quadrant` and `POST /recommend` (§4.9), the v0 scorer (§4.13), and the frontend shell with its component and end-to-end test harness (§4.10).
  - **Also implemented:** the questionnaire at `/survey`, the interactive quadrant at `/quadrant` (§4.12), the results page at `/results` (§4.14), and the four Next.js route handlers that relay them to the API server-side (§4.11, §4.14).
  - **Not implemented:** the sizing map (W3-2) and corpus-backed confidence (W3-4); NLP extraction and aggregation; evaluation. The unbuilt modules exist as documented stubs (§7). The pure `q*` function (§4.8) is called by survey capture (W4'-4a, part), but the questionnaire does not yet ask for the comfort-vs-performance goal (W6-4, §12).
- **Current binding constraint:** **no corpus source is cleared.** YouTube collection failed a terms review, Reddit access is pending, and forum terms are unreviewed (`timeline.md` §10.2; D11 reopened). The planned first release (D7) is designed to work **without** a corpus, on hand- and spec-derived placements.

---

## 2. Component diagram

Solid boxes are implemented; dashed boxes are stubs or planned.

```mermaid
flowchart LR
  subgraph Catalogue["Catalogue layer — implemented"]
    YAML[shoes.yaml<br/>30 hand-placed shoes]
    VAL[validate.py<br/>structural + domain checks]
    PRI[priors.py<br/>specs → x,y model]
    SEED[seed.py<br/>3-pass idempotent loader]
  end

  subgraph DB["PostgreSQL — implemented"]
    SHOE[(shoe)]
    ALIAS[(shoe_alias)]
    SIZE[(shoe_size_map)]
    SURV[(user_survey)]
    REC[(recommendation)]
  end

  subgraph Collect["Corpus collection — implemented, no source cleared"]
    COLL[collector.py<br/>Collector]
    YT[YouTubeSource]
    FOR[ForumSource<br/>stub]
    RED[RedditSource<br/>stub]
    LEDGER[QuotaLedger]
    LAND[(SQLite landing store<br/>raw_document · collection_run · api_quota)]
  end

  subgraph Survey["Survey layer — implemented"]
    SCH[schema.py<br/>scalar + shape validation]
    ANC[anchors.py<br/>anchor resolution]
    STO[store.py<br/>token + insert]
    PREF[preferences.py<br/>preferences → q*]
  end

  subgraph HTTP["HTTP API — implemented"]
    MAIN[main.py<br/>app + error handlers]
    DEPS[api/deps.py<br/>body · connection · catalogue]
    RSURV[POST /survey]
    RSHOE[GET /shoes]
    RQUAD[GET /quadrant]
    RREC[POST /recommend]
  end

  subgraph Scorer["Scorer — implemented"]
    SCORE[recommend/<br/>scorer_config · style · fit · confidence · score]
  end

  CFG[config.py<br/>load_dotenv]

  YAML --> VAL --> SEED --> SHOE
  SEED --> ALIAS
  PRI -. fitted against .-> YAML
  CFG --> SEED
  CFG --> COLL
  COLL --> YT & FOR & RED
  YT --> LEDGER --> LAND
  COLL --> LAND
  SCH --> STO
  ANC --> STO
  ANC --> SHOE & ALIAS
  STO --> SURV
  PREF -->|"q*"| STO
  MAIN --> RSURV
  MAIN --> RSHOE
  MAIN --> RQUAD
  DEPS --> RSURV
  DEPS --> RSHOE
  DEPS --> RQUAD
  CFG --> DEPS
  RSURV --> STO
  RSHOE --> SHOE
  RQUAD --> SHOE
  MAIN --> RREC
  DEPS --> RREC
  RREC --> SCORE
  RREC --> SURV & SHOE & SIZE & REC
  SCORE --> PREF

  NLP[nlp/<br/>extract · aggregate]:::planned
  EVAL[eval/<br/>gearlab_map · metrics · calibrate]:::planned
  SHELL[Next.js shell<br/>layout · home page]
  SURVEYUI[Questionnaire /survey<br/>form · anchor picker]
  QUADUI[Quadrant /quadrant<br/>chart · table]
  RELAY[Route handlers<br/>/api/shoes · /api/survey · /api/quadrant · /api/recommend]
  WEB[Results page<br/>/results]

  SHELL --> SURVEYUI
  SHELL --> QUADUI
  SURVEYUI -->|same origin| RELAY
  QUADUI -->|same origin| RELAY
  RELAY -->|server-side| RSHOE
  RELAY -->|server-side| RSURV
  RELAY -->|server-side| RQUAD
  WEB -->|same origin| RELAY
  RELAY -->|server-side| RREC
  LAND -.-> NLP -.-> SHOE
  EVAL -.-> NLP

  classDef planned stroke-dasharray: 5 5
```

---

## 3. Repository layout

| Path | Role | Status |
|---|---|---|
| `backend/app/catalog/data/shoes.yaml` | Seed catalogue; source of truth for shoes | Implemented |
| `backend/app/catalog/validate.py` | Catalogue validation | Implemented |
| `backend/app/catalog/priors.py` | Spec → quadrant placement model | Implemented |
| `backend/app/catalog/seed.py` | Catalogue → PostgreSQL loader | Implemented |
| `backend/app/catalog/sizing.py` | Per-brand sizing map | Stub |
| `backend/app/config.py` | `.env` loading | Implemented |
| `backend/app/db/migrations/0001_init.sql` | Product schema | Implemented |
| `backend/app/db/migrations/0001_init_down.sql` | Reversal of the above | Implemented |
| `backend/app/db/client.py`, `models.py` | Database client, typed models | Stub |
| `backend/app/scraping/collector.py` | Collector, sources, quota ledger, landing store | Implemented |
| `backend/app/scraping/{sources,youtube,reddit,rate_limiter,compile,mentions}.py` | Originally planned per-module split for collection | Stub (§7) |
| `backend/app/main.py`, `backend/app/api/deps.py` | FastAPI app, error handlers; body parsing, connection and catalogue dependencies | Implemented (§4.9) |
| `backend/app/api/routes/survey.py`, `shoes.py`, `quadrant.py` | `POST /survey`, `GET /shoes`, `GET /quadrant` | Implemented (§4.9) |
| `backend/app/api/routes/recommend.py` | `POST /recommend` | Implemented (§4.9) |
| `backend/app/survey/` | Survey capture: `schema.py` validation, `anchors.py` catalogue resolution, `store.py` persistence; `preferences.py` preference → `q*` derivation | Implemented (§4.7, §4.8) |
| `backend/app/recommend/` | Scorer: `scorer_config.py` constants, `style.py`, `fit.py`, `confidence.py`, `score.py` | Implemented (§4.13) |
| `backend/app/nlp/` | Extraction, aggregation, lexicon, distillation | Stub |
| `backend/app/eval/` | Calibration and metrics | Stub |
| `backend/tests/` | Tests: 12 implemented files (six of them for the scorer), 2 stubs (`test_aggregate.py`, `test_calibration.py`) | Partial |
| `backend/data/` | Local data: `gearlab/` placeholder; landing store (gitignored) | Runtime |
| `frontend/` | The Next.js application, a self-contained npm project with its own manifest, lockfile, configuration and `.gitignore`. The repository root has no `package.json` | Implemented (§4.10) |
| `frontend/src/app/layout.tsx`, `page.tsx`, `globals.css` | Next.js App Router root layout, home page, global stylesheet with the quadrant page's colour tokens | Implemented (§4.10) |
| `frontend/src/app/survey/`, `components/`, `lib/` | Questionnaire page, form and anchor picker, browser client, types, vocabularies, payload builder | Implemented (§4.11) |
| `frontend/src/app/api/` | Route handlers `GET /api/shoes`, `POST /api/survey`, `GET /api/quadrant` and `POST /api/recommend`, relaying to the API server-side | Implemented (§4.11, §4.14) |
| `frontend/src/app/quadrant/`, `components/Quadrant{Chart,Table}.tsx`, `lib/quadrant-scale.ts`, `quadrant-labels.ts`, `format-axis-value.ts` | Quadrant page, interactive chart, table alternative and their shared helpers | Implemented (§4.12) |
| `frontend/src/app/results/`, `frontend/src/app/api/recommend/` | Ranked results page, `ResultCard`, `recommendation-copy.ts`, and the `/api/recommend` route handler | Implemented (§4.14) |
| `frontend/src/app/page.test.tsx`, `frontend/e2e/` | Component test (Vitest) and end-to-end specs (Playwright) | Implemented (§4.10, §11) |
| `frontend/package.json`, `frontend/package-lock.json` | npm manifest, scripts and committed lockfile | Implemented (§10.2) |
| `frontend/vitest.config.mts`, `vitest.setup.ts`, `playwright.config.ts` | Test-runner configuration | Implemented (§4.10) |
| `.github/workflows/ci.yml` | Continuous integration: two backend jobs and one frontend job | Implemented (§11) |
| `scaffold.sh` | Non-destructive generator for the stub tree (54 `stub` entries; writes only files that do not exist) | Tooling |
| `backend/scraping/`, `backend/NLP/` | Empty files from an earlier layout | Dead code (§12) |
| `timeline.md`, `SETUP.md` | Plan of record; local setup | Docs |

---

## 4. Implemented components

### 4.1 Catalogue — `backend/app/catalog/data/shoes.yaml`
- **Shape:** a mapping root with a `shoes` list. Each entry has `brand`, `model`, optional `version`, `gender`, `last_shape`, `downturn`, `stiffness_spec`, `closure`, `rubber`, `msrp_usd`, `quadrant_x_prior`, `quadrant_y_prior`, `prior_source`, `aliases`, and optional `anchor` and `note`.
- **Contents:** 30 shoes and 71 aliases, all `prior_source: hand`. `msrp_usd` is set on 23 rows (2026-11-05): 19 from the brand's US site and 4 medium-confidence list prices (Testarossa, Altura, Aragon, Hiangle). It is null on 7 (Anasazi Pro, Mythos, Maestro Mid, Astroman, Katana Velcro, Elektra, Moccasym). Each value's source and confidence sit in a `# msrp:` comment above it. A null is an unresolved price, not a zero, so `validate.py --require-msrp` fails by design until the seven are resolved.
- **Anchors:** five shoes marked `anchor: true` are calibration ground truth for the quadrant — La Sportiva Solution (Q1), La Sportiva TC Pro (Q2), Evolv Defy (Q3), Scarpa Drago (Q4), Scarpa Instinct VSR (Q4).
- **Identity:** `(brand, model, version, gender)`. A `version` that changes the last is a separate shoe — the Solution (Q1) and Solution Comp (Q4) are separate rows in different quadrants.
- `anchor` and `note` are metadata and documentation; they are not persisted.

### 4.2 Catalogue validation — `backend/app/catalog/validate.py`
- **Interface:** `validate(path=CATALOG, require_msrp=False) -> list[str]` (an empty list means valid); `quadrant(x, y) -> str`; CLI `python3 backend/app/catalog/validate.py [--catalog PATH] [--require-msrp]`, exit code 1 on errors.
- **Order of checks:** structure first (a mapping root, `shoes` as a list, each entry a mapping); then field types (identity fields are strings; priors and `msrp_usd` are numbers, not booleans; `aliases` is a list of strings); then domain rules. Malformed input returns errors and never raises.
- **Domain rules** (several mirror database constraints so failures surface before load):
  - count within `MIN_SHOES`–`MAX_SHOES` (currently 25–30)
  - the five anchors are marked `anchor: true` and land in their expected quadrants
  - `gender`, `downturn` and `closure` enums match the SQL `CHECK` constraints
  - `prior_source` ∈ {`corpus`, `hand`, `spec`}, present exactly when coordinates are present
  - priors lie in `[-1,1]` and not exactly on an axis
  - `(brand, model, version, gender)` is unique
  - aliases are unique across the whole catalogue, case-insensitively
- **Budget-gate guard:** by default null prices only warn; `--require-msrp` makes them errors. This check must pass before any budget filtering relies on prices. Today it warns 7/30 and `--require-msrp` fails on those seven (§4.1).

### 4.3 Placement model — `backend/app/catalog/priors.py`
- **Interface:** `derive_prior(shoe: dict) -> (x, y)`; `refit(shoes) -> dict` (weights plus LOOCV scores); `quadrant(x, y)`; the `PriorSource` enum (`CORPUS`, `HAND`, `SPEC`); CLI `python3 backend/app/catalog/priors.py [--refit] [--catalog PATH]`.
- **Model:** linear, over an 18-feature vector:
  - bias
  - one-hot `downturn` (3), `last_shape` (3), `stiffness_spec` (6), `closure` (3)
  - interaction `flat_and_stiff` — a flat last with a stiff or moderate-stiff midsole
  - interaction `soft_slipper` — a slipper closure with a soft or very soft midsole
- **Why the interactions:** a flat last alone predicts comfort, but a flat *and* stiff shoe is a precision edging shoe. `flat_and_stiff` carries x-weight +0.322.
- **Output contract:** clamped to `[-1,1]`; an exact zero is nudged to −0.001 (the comfort/stiff side) so every placement has a quadrant; rounded to 3 decimals to match `NUMERIC(4,3)`.
- **Fitting:** `refit()` fits by numpy least squares and scores the fit under leave-one-out cross-validation. `WEIGHTS` holds the checked-in output of `refit()` on the hand-placed set, so behaviour is deterministic and reproducible. numpy is needed only for refitting; `derive_prior()` is pure Python.
- **Measured accuracy** on the 30 hand-placed shoes: LOOCV MAE x **0.139**, y **0.113**; quadrant agreement **26/30 (87%)**.
- **Role:** makes catalogue growth cheap — a new shoe needs manufacturer spec fields, not a per-shoe judgement call.
- **Limitation:** the model is fitted to a single rater's placements, so its accuracy is agreement with that rater. An independent rater panel is planned (W0-4a).

### 4.4 Catalogue loader — `backend/app/catalog/seed.py`
- **Interface:** `load_catalog(path) -> list[dict]` (validates first; raises `ValueError` if invalid); `seed(conn, shoes, dry_run=False) -> SeedResult`; CLI `python3 backend/app/catalog/seed.py [--catalog PATH] [--database-url URL] [--dry-run]`.
- **Persisted columns** (`COLUMNS`, 13): `brand, model, version, gender, last_shape, downturn, stiffness_spec, closure, rubber, msrp_usd, quadrant_x_prior, quadrant_y_prior, prior_source`.
- **Algorithm — three passes in one transaction:**
  1. Upsert every shoe with `INSERT … ON CONFLICT (brand, model, version, gender) DO UPDATE … RETURNING id, (xmax = 0)`, collecting each ID and whether it was inserted or updated.
  2. `DELETE FROM shoe_alias WHERE shoe_id = ANY(<all collected ids>)`.
  3. Insert every shoe's current aliases.
- **Why three passes:** aliases are unique across the whole table, so per-shoe delete-and-insert depends on order. An alias moving from a later catalogue entry to an earlier one collides with the not-yet-deleted row and aborts the transaction; clearing every affected alias first removes the dependency.
- **Idempotency:** re-seeding an unchanged catalogue updates rows in place. Shoe UUIDs survive re-seeds, which matters because `recommendation.shoe_id` references them.
- **Normalisation:** `version` becomes `''` rather than NULL — NULL never equals NULL, which would defeat the upsert. `gender` defaults to `unisex`.
- **Replace, not merge:** removing an alias from the catalogue removes it from the database.
- **Failure behaviour:** invalid catalogue → exit 1 before any connection; missing `DATABASE_URL` → exit 2; missing `shoe` table → exit 1 with a migration hint; connection failure → exit 1; `--dry-run` rolls back.

### 4.5 Configuration — `backend/app/config.py`
- **Interface:** `load_dotenv(path=None, override=False) -> list[str]`; `configured(*keys) -> dict[str, bool]`; `PROJECT_ROOT`; `DEFAULT_ENV` (the repository-root `.env`).
- **Semantics:**
  - Returns the **names** of the keys it set, never values; `configured()` returns booleans. Secrets cannot leak through return values.
  - Variables already in the process environment take precedence over the file unless `override=True`.
  - Supports `#` comments, an `export ` prefix, spaces around `=`, and one pair of matching surrounding quotes. An empty assignment means *unset*.
  - A missing file returns `[]`, so real environment variables work identically without a file.
- **Dependency choice:** standard library only, so entry points cannot fail to start over an unrelated package.
- **Variables read by implemented code:**

| Variable | Used by | Required |
|---|---|---|
| `DATABASE_URL` | `seed.py` | For seeding |
| `CRUXUP_AUTHOR_SALT` | `collector.py` | For collection — no default |
| `YOUTUBE_API_KEY` | `YouTubeSource` | Source skipped without it |
| `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT` | `RedditSource` | Source skipped without them |

- `SUPABASE_URL`, `SUPABASE_KEY` and `ANTHROPIC_API_KEY` appear in `.env.example` but are not read by any implemented code.

### 4.6 Corpus collector — `backend/app/scraping/collector.py`

#### Structure
- **`Source`** (abstract): `available() -> (bool, reason)` never raises, and unavailability is a normal state; `collect(query, limit) -> list[RawDocument]`.
- **`RawDocument`** (frozen dataclass): `source`, `external_id`, `body`, `permalink`, `created_utc`, `author_hash`, `payload`.
- **`YouTubeSource`** is implemented. **`ForumSource`** and **`RedditSource`** implement `available()`, but their `collect()` raises `NotImplementedError`.
- **`Collector`** runs every *available* source over every query:
  - skips unavailable sources with a log line
  - records every run
  - stops a source on `NotImplementedError`
  - isolates other per-query failures
  - waits 1 s between queries
- **`LandingStore`** — a local SQLite store, `backend/data/corpus_landing.sqlite3` by default.
- **`QuotaLedger`** — persistent quota accounting (below).
- **CLI:** `python3 backend/app/scraping/collector.py [--limit N] [--db PATH] [--status] [-v]`. `--status` prints documents per day and today's quota usage.

#### YouTube adapter
- Calls `search.list` (type `video`, `relevanceLanguage=en`, `videos_per_query` = 5 by default), then `commentThreads.list` per video (`textFormat=plainText`, `order=relevance`, paginated up to the limit).
- **Transport is injectable** (`fetch`), so the adapter is fully testable offline. The default transport uses stdlib `urllib` and maps HTTP 403 quota responses to `QuotaExceeded`.
- A video with comments disabled is skipped without failing the run; an unparseable timestamp keeps the document with `created_utc = None`; empty comment bodies are dropped.
- **Stored per document:** the comment ID as `external_id`, the text, a permalink (`watch?v=<video>&lc=<comment>`), the timestamp, the author hash, and `payload = {video_id, like_count}`. `authorDisplayName` is never stored.

#### Quota accounting
- **Buckets**, following YouTube's published quota model:

| Bucket | Endpoints | Cost | Daily limit |
|---|---|---|---|
| `youtube.search` | `search.list` | 1 per call | 100 calls |
| `youtube.units` | all others, including `commentThreads.list` | 1 per call | 10,000 units |

- **Reserved before the request.** YouTube charges quota for every request, including invalid ones, so quota is reserved atomically first: `INSERT OR IGNORE` the day's row, then `UPDATE … SET used = used + cost WHERE used + cost <= limit`. Zero rows updated means `QuotaExceeded`.
- **Persistence:** counters live in the landing store keyed by `(day, bucket)`, so separate processes on the same day share one budget.
- **Day boundary:** `America/Los_Angeles`, matching YouTube's midnight-Pacific reset.
- **On exhaustion,** `collect()` returns the documents gathered so far rather than failing.
- `QuotaLedger.in_memory()` exists for tests and library use; the CLI always injects the persistent ledger.

#### Author pseudonymisation
- `author_hash = HMAC-SHA256(key = CRUXUP_AUTHOR_SALT, message = author channel ID)`, hex-encoded.
- The key is read **when a hash is computed**, not at import, so a value loaded from `.env` after import is honoured.
- **Fails closed:** there is no default key. A missing key, one shorter than 32 characters, or a known-compromised value raises `MissingAuthorSalt`. The CLI checks the key after loading configuration and exits with code 2 **before any network request**.
- **The key is a secret.** Author IDs are public, so anyone holding the key could recompute hashes for candidate IDs. Changing the key makes previously stored hashes incomparable.

#### Landing store schema (SQLite)
| Table | Key | Columns |
|---|---|---|
| `raw_document` | `(source, external_id)` | `body, permalink, created_utc, author_hash, payload_json, collected_at` |
| `collection_run` | `id` | `started_at, finished_at, source, query, fetched, inserted, error` |
| `api_quota` | `(day, bucket)` | `used` |

- `INSERT OR IGNORE` on the primary key makes collection idempotent across restarts.
- The landing store holds raw payloads. Normalising them into the PostgreSQL corpus schema is planned (W1-full). **Retention is set by each source's terms** — YouTube caps stored data at 30 days.
- The store is gitignored (`backend/data/*.sqlite3`) and **currently empty**.

---

### 4.7 Survey capture — `backend/app/survey/`

Loads one questionnaire submission into `user_survey`. It adds no DDL: the table
and its CHECK constraints already exist in `0001_init.sql`, and this layer is the
validation and loading path in front of them.

#### Structure
- **`schema.py`** — `validate(payload) -> list[str]`. Scalar fields and top-level
  shape only; accumulates every problem rather than raising on the first, matching
  `catalog/validate.py`. CLI: `python3 backend/app/survey/schema.py <payload.json>`.
- **`anchors.py`** — resolves anchor sets *G* (`known_good_shoes`) and *B*
  (`known_bad_shoes`) against the catalogue.
  - **`CatalogLookup`** (Protocol) with two implementations: **`StaticCatalog`**
    (in-memory, used by the hermetic tests) and **`PostgresCatalog`** (reads
    `shoe` / `shoe_alias` from an already-open connection, never opening its own).
  - **`CatalogShoe`** (frozen dataclass) projects exactly `shoe_unique_identity`
    plus the id.
  - `resolve_anchors(good, bad, catalog)` returns resolved lists plus errors.
- **`store.py`** — `build_survey_row()` merges both validation stages into one
  error list; `insert_survey()` writes one row in a single transaction. CLI:
  `python3 backend/app/survey/store.py <payload.json> [--dry-run]`.

#### Vocabularies and the schema they mirror
`schema.ENUMS` mirrors five CHECK constraints (`survey_width_valid`,
`survey_instep_valid`, `survey_toe_valid`, `survey_arch_valid`,
`survey_disc_valid`). A test parses those constraints back out of the migration
and asserts equality, so the two cannot drift silently.

`heel_fit`, `terrain` and `level` have **no** CHECK constraint in the schema, so
they are validated only in Python (`schema.PY_ONLY_ENUMS`). This asymmetry is
deliberate and tracked — see §12.

#### Resolution rules
- Matching is case-insensitive on `(brand, model)`, narrowed by an optional
  `version` and/or `gender`.
- **An ambiguous name is an error, never a guess.** Three catalogue entries share
  a `(brand, model)` pair and differ only by version — Scarpa Instinct (VS/VSR),
  La Sportiva Katana (Lace/Velcro), La Sportiva Solution (base/Comp). Two are §3
  calibration anchors, so silently picking one would corrupt calibration-grade
  input. The error lists every candidate.
- A registered `shoe_alias` used as the `model` is an unambiguous disambiguator,
  because `shoe_alias_globally_unique` is unique across the catalogue. It is tried
  only when the identity match found nothing, so a bare shared name stays
  ambiguous regardless of whether it happens to also be an alias.
- `size` is opaque to the catalogue: it is never gated against `shoe_size_map`
  (D9 makes `size_exists` the only hard sizing gate, decided downstream).
- The same shoe in both *G* and *B* is contradictory and is rejected.

#### Input constraints
- **Allow-lists, not deny-lists.** Unknown top-level keys and unknown anchor
  sub-keys are rejected outright, so an identifier cannot ride into storage
  through an unmodelled field (D4). `shoe_id` is an *output* of resolution and is
  refused as an input, so a caller cannot point an anchor at an arbitrary shoe.
- **`size` is bounded in length and character set.** A length cap alone is not
  sufficient — an email address is short — so the characters a brand size is
  actually written with are enumerated, which rejects an address on `@`.
- Free text is rejected if it carries a NUL byte or a lone UTF-16 surrogate;
  both are representable in a Python string but not storable, and would otherwise
  surface as an exception from inside the driver rather than a validation error.
- The number of anchors per submission is capped, because each one costs a
  catalogue round trip. The cap short-circuits resolution, so an oversized
  submission performs no lookups at all.
- Numeric fields are checked against their column **scale**, not merely their
  range: PostgreSQL silently *rounds* a value that exceeds a `NUMERIC` scale
  rather than rejecting it, so a submission could otherwise validate clean and be
  stored as a different number. The comparison carries a float tolerance, because
  `q*` is computed upstream and binary-float noise is expected.

#### Identity
`survey_token` is generated with `secrets.token_urlsafe` (CSPRNG) and is the only
identity written. It is never accepted from a submission.

### 4.8 Preference → target — `backend/app/survey/preferences.py`

Maps a user's preference answers to `q*`, the point on the quadrant plane their
recommendations are steered toward (`timeline.md` §7.5). The Style score (§7.3)
measures each shoe's distance from this point. Pure arithmetic: no database, no
IO, standard library only.

#### Interface
- **`target_quadrant(discipline, terrain=None, level=None, goal=None) -> (x, y)`**
  - `discipline` is required: `boulder`, `sport`, `trad` or `gym`.
  - `terrain` (`slab`, `vertical`, `overhang`, `crack`) and `level` (`beginner`,
    `intermediate`, `advanced`, `elite`) are optional.
  - `goal` is an optional comfort-vs-performance slider value in `[-1, 1]`
    (−1 comfort, +1 performance).
  - An omitted input contributes nothing.
  - The coordinates are rounded to 3 decimal places, the scale of
    `goal_x_target` / `goal_y_target` (`NUMERIC(4,3)`), so `q*` can be stored
    without PostgreSQL rounding it again.
- **`quadrant_of(q) -> "Q1" … "Q4"`** labels a point per §1. It raises on a
  point that lies on an axis or has a non-finite coordinate.
  `catalog/priors.quadrant()` classifies shoe placements on the same plane but
  returns an `ON-AXIS` label instead of raising. It is not shared because
  `priors.py` depends on PyYAML.

#### Mapping
Discipline chooses the quadrant. The other inputs only move `q*` *within* it.

| Input | Value | Contribution (x, y) | Rationale (`timeline.md` §3) |
|---|---|---|---|
| discipline | `sport` | (+0.55, −0.55) | Q1: performance + stiff |
| discipline | `trad` | (−0.55, −0.55) | Q2: comfort + stiff |
| discipline | `gym` | (−0.55, +0.55) | Q3: comfort + soft |
| discipline | `boulder` | (+0.55, +0.55) | Q4: performance + soft |
| terrain | `vertical` | (+0.15, −0.15) | toward Q1: technical face, edging |
| terrain | `crack` | (−0.15, −0.15) | toward Q2: all-day, multi-pitch |
| terrain | `slab` | (−0.15, +0.15) | toward Q3: slabs |
| terrain | `overhang` | (+0.15, +0.15) | toward Q4: steep terrain |
| level | `beginner` → `elite` | x only: −0.15, −0.05, +0.05, +0.15 | beginners sit on the comfort side |
| goal | `g ∈ [−1, 1]` | x only: 0.15 · g | the comfort ↔ performance axis |

The two magnitudes are named constants, `BASE_MAGNITUDE = 0.55` and
`NUDGE = 0.15`. The tables are read-only mappings.

#### Invariant: `q*` always lies inside its discipline's quadrant
On any axis, at most three nudges can oppose the discipline's sign, which caps
the total at 3 × 0.15 = 0.45. That is less than the 0.55 base, so for **every**
combination of inputs:

- `|x|` and `|y|` are at least 0.10. `q*` never lies on an axis, where no
  quadrant is defined, and never crosses into another quadrant.
- `|x|` and `|y|` are at most 0.55 + 0.45 = 1.00. `q*` stays inside `[-1, 1]²`,
  and the clamp in the code never changes a value.

This holds by construction, not by clamping. The module checks both
inequalities when it is imported and raises `RuntimeError` if a change to the
constants breaks them. The check is an explicit `raise` rather than `assert`,
because `python -O` removes assert statements.

#### Validation
- Inputs are checked in the order discipline, terrain, level, goal. The first
  problem raises `ValueError`, naming the field and its allowed values.
- A `bool` is not accepted as a number.
- `goal` must be finite and within `[-1, 1]`. An integer too large to convert to
  a float is rejected with `ValueError`, not `OverflowError`.
- Unlike `schema.validate()`, errors are not accumulated. The function sits
  downstream of submission validation, not in front of a form.

#### Vocabulary
The function keys its tables to the same vocabularies `survey/schema.py`
accepts. `preferences.py` does not import `schema.py`, so tests pin the two
together: the discipline, terrain and level keys, and the output precision
(`OUTPUT_DECIMALS` = `schema.GOAL_TARGET_DECIMALS`).

#### Not yet modelled
- **Stiffness preference** and **downsizing/pain tolerance** are listed in §7.5
  but have no mapping and no `user_survey` column.
- **The raw `goal` is not stored.** `store._prepare_submission()` (called by
  `build_survey_row()`) derives `goal_x_target` / `goal_y_target` from it at
  capture and then drops it; no column holds it or a mapping version (W4'-4b).
  See §12.

### 4.9 HTTP API — `backend/app/main.py`, `backend/app/api/`

A FastAPI service over the survey layer (§4.7), the catalogue (W7-1) and the
scorer (§4.13). It has four endpoints; `POST /recommend` (W7-2) ranks one survey.

| File | Role |
|---|---|
| `main.py` | `create_app()` factory and module-level `app`; mounts the four routers; exception handlers |
| `api/deps.py` | `json_body` (request-body parsing), `survey_token_body` (the `POST /recommend` body), `database_url()`, `get_conn()` (one connection per request), `get_catalog()` |
| `api/routes/survey.py` | `POST /survey` |
| `api/routes/shoes.py` | `GET /shoes` |
| `api/routes/quadrant.py` | `GET /quadrant` |
| `api/routes/recommend.py` | `POST /recommend` |

- **Running:** `cd backend && uvicorn app.main:app`, which binds `127.0.0.1:8000`
  by default. `app` is a package rooted at `backend/`. The survey modules are
  imported flat through their own directory, the way `store.py` imports its
  siblings, so the service and `store.py` share one `anchors` module object.
- **`POST /survey`** is a thin wrapper. It calls
  `build_survey_row(payload, PostgresCatalog(conn))`, then
  `insert_survey(conn, row)`. It has no request model and no checks of its own,
  so its rules cannot drift from `survey/`.

  | Outcome | Status | Body |
  |---|---|---|
  | Valid submission | 201 | `{"survey_token": "..."}`; nothing else is echoed |
  | Invalid submission | 422 | `{"errors": [...]}`: `build_survey_row`'s list verbatim, every error in one response. Nothing is written |
  | Body does not parse (malformed syntax, invalid UTF-8, nesting past the parser's recursion limit) | 422 | `{"errors": ["request body is not valid JSON"]}` |
  | Database unreachable, or `DATABASE_URL` unset | 503 | `{"detail": "database unavailable"}` |
  | Any other database or unexpected error | 500 | `{"detail": "could not complete the request"}` |

  - **Non-object bodies:** a body that parses but is not an object (an array,
    string, number, `null` or empty body, or a non-JSON content type) is passed
    to `build_survey_row`, which rejects it. The API adds no shape rule of its own.
  - **Invalid submissions read but never write:** anchor resolution reads the
    catalogue even for an invalid submission, so every error is reported at
    once. Nothing is committed on that path; the connection is closed without a
    commit, which discards the read transaction.
- **Body parsing** happens in `deps.json_body`, not FastAPI's `Body()`.
  - FastAPI turns only a `JSONDecodeError` into its validation error. A
    `RecursionError` (deep nesting) or `UnicodeDecodeError` (invalid UTF-8)
    became a 400 of a different shape, which no handler saw and which was
    never logged.
  - `json_body` catches `(ValueError, RecursionError)`, the same pair
    `store.main()` catches. Otherwise it follows `Body()`'s rules: an empty
    body is `null`; JSON is parsed with no content type, or with
    `application/json` or `application/*+json`; any other content type passes
    through as raw bytes.
  - A test pins that `/survey` declares no request body or parameters to
    FastAPI, so the framework can never validate anything ahead of
    `build_survey_row`. As a consequence, `/docs` shows no request schema
    for `/survey`. The payload shape is `survey/schema.py` (§4.7), which is
    not duplicated in OpenAPI so the two cannot drift.
- **`GET /shoes`** returns every `shoe` row as
  `{id, brand, model, version, gender}`, ordered by brand, model, version and
  gender. `version` is `''` for a base model.
  - **Why `version` and `gender`:** they distinguish the three pairs that share
    `(brand, model)`. A test proves that every returned item, submitted back as
    an anchor, resolves to exactly its own `id`, so a picker built on this list
    cannot produce an ambiguous anchor.
  - **No `status` filter,** because anchor resolution matches shoes of any
    status.
  - **No pagination.** The catalogue has 30 rows today and ~100 under D12.
- **`GET /quadrant`** (W6-2) returns every shoe that has a quadrant prior, as
  `{id, brand, model, version, gender, x, y, prior_source, is_anchor, quadrant}`.
  It has its own router, because `GET /shoes` is pinned to identity columns
  for the anchor picker.
  - **Filter and order:** `quadrant_x_prior IS NOT NULL`. The paired CHECKs
    make `y` and `prior_source` all-or-nothing with `x`, so no further guard
    is needed. The order is `lower(brand), lower(model), version, gender,
    brand, model, id`, which is total.
  - **`is_anchor`** is membership of `(brand, model, version)` in
    `validate.ANCHORS`, the single source of the §3 anchors. Nothing is
    stored: `seed.py` drops the YAML flag and there is no column. The key has
    no gender, so a gendered twin of an anchor would be flagged too (§12).
  - **`quadrant`** is `priors.quadrant(x, y)`. An on-axis prior is outside the
    `Q1`–`Q4` literal, so response validation fails and the handler returns
    the same masked 500 as any unexpected error. That is deliberate:
    `validate.py` treats an on-axis prior as a catalogue bug.
  - **Numbers:** `NUMERIC(4,3)` arrives as `Decimal` and is converted to
    `float`, so the JSON carries numbers.
  - **Parameters:** the SQL takes no bind parameters. The handler is a plain
    `def`, as the other routes are.
- **`POST /recommend`** (W7-2) ranks the active catalogue for one survey with
  the scorer in §4.13 and stores the ranking. The body must be exactly
  `{"survey_token": <token>}`.

  | Outcome | Status | Body |
  |---|---|---|
  | Ranking returned | 200 | `RecommendOut` (below) |
  | Unknown token | 404 | `{"errors": ["survey not found"]}` |
  | Body is not exactly that object, including an empty body | 422 | `{"errors": ['body must be {"survey_token": <token>}']}` |
  | Body is not valid JSON | 422 | `{"errors": ["request body is not valid JSON"]}` |
  | Database unreachable, or `DATABASE_URL` unset | 503 | `{"detail": "database unavailable"}` |
  | Any other failure, including a response that fails validation | 500 | `{"detail": "could not complete the request"}` |

  - **The body is checked before any connection.** `deps.survey_token_body`
    reads the body through `json_body` and is declared before `get_conn`, so a
    bad body never opens a connection. The token must match
    `[A-Za-z0-9_-]{1,64}`. The 422 text is fixed and never echoes the value; the
    route declares no request model, because FastAPI's own 422 echoes `input`.
  - **One transaction.** The survey row is read `FOR UPDATE`, so concurrent
    requests for one token serialise. Every shoe is read with no status filter,
    because anchors must resolve against discontinued shoes; the scorer keeps
    only active candidates. Size rows are read only for the survey's street
    size. The token is only ever a bound parameter. The lock wait is bounded by
    `SET LOCAL lock_timeout = '5s'`; a timeout is an `OperationalError`, so it
    is the masked 503.
  - **Upsert, delete, validate, commit.** Each ranked shoe is upserted on
    `(survey_id, shoe_id)`; the conflict clause rewrites only the score columns,
    `rank`, `scorer_version` and `created_at`, never the feedback columns. A row
    that already carries feedback (`feedback_at` set) is not updated at all
    (`DO UPDATE … WHERE recommendation.feedback_at IS NULL`): it stays the
    record of what the user was shown, so its stored rank and scores can differ
    from the response. Rows for shoes the new
    ranking no longer contains are deleted unless they carry feedback. Then
    `RecommendOut` is validated (NaN and infinity rejected) and only then is the
    transaction committed, once. A validation failure becomes the generic 500
    and the rows are rolled back.
  - **Response** (`RecommendOut`): `scorer_version`, `target` (`{x, y}` or
    null), `terms`, `gated_out`, `warnings` and `results`. Each result is a
    `QuadrantShoeOut` plus the scoring fields in §4.13, so W6-3 can reuse
    `QuadrantChart`. There is no `outcome` or `assessed` field (`timeline.md`
    §13).
  - **Not in the endpoint:** a rate limit and a gender filter (§12). The
    The Next.js route handler `/api/recommend` forwards to it (§4.14).
- **Connections:** `get_conn()` opens one psycopg connection per request, with
  `connect_timeout=5`. The catalogue reads and the insert share it, and it is
  always closed. `POST /recommend` reads and writes on its one connection and
  commits once. There is no pool, so concurrent requests each hold their
  own connection against the server's `max_connections`.
- **Configuration:** `DATABASE_URL` is resolved at request time, from the
  environment first and then `.env`. With no value, the API fails closed with
  a 503 rather than guessing a database.
- **Error hygiene:** response bodies are fixed strings, with no exception text,
  DSN, SQL or submitted content. The server log records only the exception
  class, the class of any chained cause, the method and the path.
- **Deliberately not in the service:**
  - no CORS middleware, because the browser never calls it directly (§8);
  - no request-size limit;
  - `/docs` and `/openapi.json` stay enabled.

  The Next.js route handlers are the internet-facing layer and own these
  controls (§4.11, §12).
- **`q*` is derived in the store, not the route.** `build_survey_row()` calls
  `preferences.target_quadrant()` and refuses a caller-supplied
  `goal_x_target` / `goal_y_target`, so the route still adds no validation (§12).

### 4.10 Frontend shell and test harness — `frontend/`

The minimum the Next.js App Router needs in order to build, plus the two test layers that later frontend work builds on (W6-0). The questionnaire built on it is described in §4.11 and the quadrant page in §4.12; the results page is described in §4.14.

Everything in this section lives in `frontend/`, a self-contained npm project. Paths below are relative to it, and every `npm` command runs there.

#### Structure
| File | Role |
|---|---|
| `src/app/layout.tsx` | Root layout, a server component. Renders `<html lang="en">` and `<body>`, imports `globals.css`, and exports `metadata` (title `CruxUp` and a one-line description). |
| `src/app/page.tsx` | Home page, a server component: an `<h1>`, one sentence describing the product, and two `next/link`s, to `/survey` and `/quadrant`. |
| `src/app/globals.css` | `@import "tailwindcss";` and an `@theme` block of semantic colour tokens (`background`, `surface`, `foreground`, `muted`, `border`, `control-border`, `accent`, `accent-foreground`, `danger`, `focus-ring`) plus `radius-control`. Only the quadrant page (§4.12) uses them; the questionnaire keeps Tailwind palette classes. Light values only, because the app has no dark mode. |
| `src/app/results/page.tsx` | Results page shell; the ranked view is in §4.14. |
| `vitest.config.mts`, `vitest.setup.ts` | Component-test configuration, coverage thresholds and per-test setup. |
| `playwright.config.ts`, `e2e/` | End-to-end configuration, specs, and the mock API with its catalogue fixture. |
| `.env.example` | Documents `CRUXUP_API_URL`, the backend address the route handlers use (§4.11). |

#### Build output
- `next build` prerenders `/`, `/_not-found`, `/survey`, `/results` and `/quadrant` as static content (○). The route handlers `/api/survey`, `/api/shoes`, `/api/quadrant` and `/api/recommend` are dynamic (ƒ).
- Route handlers and client components exist (§4.11, §4.12). There is no middleware and no server action.
- **No web fonts are loaded.** `next/font/google` would download fonts during `next build`, which would make the build depend on network access.
- **Module alias:** `@/*` resolves to `src/*`, in both `tsconfig.json` and Vitest (`resolve.tsconfigPaths`). Nothing imports through it yet.

#### Test layers
| Layer | Tool | Location | Runs against | Covers |
|---|---|---|---|---|
| Component | Vitest 4 + React Testing Library | `src/**/*.test.{ts,tsx}` | jsdom | One component's rendered, accessible structure. Synchronous server components render directly. |
| End-to-end | Playwright, Chromium only | `e2e/*.spec.ts` | A real Next.js server on port 3100, relaying to a mock API on port 8100 | Routing, keyboard flows, what the relay forwards, request origins, the quadrant page's tooltip and phone-width behaviour, and automated accessibility scans. |

- **Vitest:**
  - `vitest.setup.ts` registers the `@testing-library/jest-dom` matchers, stubs `scrollIntoView` (absent in jsdom), and unmounts after every test.
  - Route-handler tests run in Node rather than jsdom (`// @vitest-environment node`).
  - `npm run test:coverage` enforces thresholds of 80% lines, statements and functions and 75% branches on `src/app/{api,components,lib}/**`. Pages and the layout are covered by Playwright instead.
  - Test APIs are imported explicitly rather than injected as globals.
  - Vitest includes only `src/`, and Playwright reads only `e2e/`, so neither runner picks up the other's files.
- **Async server components** cannot be rendered by React Testing Library. They belong to the Playwright layer.
- **Playwright servers:**
  - `e2e/mock-api.mjs` is a dependency-free stand-in for the API on port 8100. It serves `GET /shoes` from `e2e/fixtures/shoes.json` (the 30 real catalogue rows, with synthetic ids), `GET /quadrant` from `e2e/fixtures/quadrant.json` (the seeded API's own `GET /quadrant` response, with the same synthetic ids), and records each `POST /survey` body for assertions. It validates nothing, with one exception: a size containing a comma gets the API's exact size-error message, so the plain-language translation is exercised end to end. The real API's rules are covered by its own tests (§11).
  - The Next.js server is started with `CRUXUP_API_URL` pointing at the mock.
  - Locally it starts `next dev`, and an already-running server on port 3100 is reused.
  - When `CI` is set, it starts `next start` against the build made by the preceding CI step, so CI exercises production output.
  - Retries (2) and `forbidOnly` apply in CI only.
  - Port 3100 avoids colliding with a development server on the default 3000.

#### Toolchain
- **Location:** `frontend/` holds the manifest, lockfile, `tsconfig.json`, the ESLint, PostCSS, Next.js and test-runner configs, and a `.gitignore` for dependencies, build output and test artifacts. No lockfile exists above it, so Next.js treats `frontend/` as the project root without configuration.
- **Package manager:** npm, with a committed `package-lock.json` (lockfile v3). `npm ci` reproduces the install.
- **Pinning:** `next` and `eslint-config-next` are pinned exactly, at the same version. `engines.node` is `>=20.9.0`, the Next.js 16 minimum.
- **Lint:** ESLint 9 flat config, using `eslint-config-next` `core-web-vitals` + `typescript`. It ignores coverage and Playwright output. A `.venv/**` ignore entry remains from when the app lived at the repository root; it no longer matches anything.
  - Next.js 16's `next build` does not run ESLint, so lint is a separate CI step.
- **Type-check:** `tsc --noEmit` (`npm run typecheck`). `next build` also type-checks every file that `tsconfig.json` includes, test files and configs among them.
  - Its `**/*.ts`, `**/*.tsx` and `**/*.mts` include globs are scoped to `frontend/`, so the type-checker never reaches `backend/` or `.venv/`.

### 4.11 Questionnaire and relay — `frontend/src/app/{survey,components,lib,api}/`

The questionnaire that captures a survey (W6-1), and the relay that also serves the quadrant page (W6-2, §4.12). The browser talks only to the app's own origin. Four route handlers relay its requests to the API server-side, so the API is never addressed by the client (§8). Paths below are relative to `frontend/src/app/`.

#### Structure
| File | Role |
|---|---|
| `survey/page.tsx` | Server component. Title "Questionnaire \| CruxUp", one `<h1>`, a short introduction, and `<SurveyForm />`. Prerendered as static content. |
| `components/SurveyForm.tsx` | Client component. Loads the catalogue once, holds the answers, builds and submits the payload, and renders the outcome. |
| `components/AnchorPicker.tsx` | Client component. Catalogue autocomplete for one anchor list. There are two instances: "Shoes that fit you well" (`known_good_shoes`) and "Shoes that fit you badly" (`known_bad_shoes`). |
| `lib/types.ts` | Types mirroring the API: `Shoe`, `Gender`, the vocabulary unions, `AnchorEntry`, `SurveyPayload`, `QuadrantShoe` with `PriorSource` and `Quadrant`, and the response bodies. `backend/tests/test_frontend_contract.py` parses the unions and interface keys and compares them with `schema.py`, `anchors.py`, `ShoeOut` and `QuadrantShoeOut`. |
| `lib/vocab.ts` | Option values and labels for every select, and the street-size and budget bounds. |
| `lib/payload.ts` | Pure function from form state to request body. |
| `lib/errors.ts` | Turns the API's 422 messages into plain-language text, linked to the field they concern where recognised. |
| `lib/shoe.ts` | The display name of a shoe ("Scarpa Instinct VSR (unisex)"), shared by the picker, the error text and the quadrant chart and table. |
| `lib/api.ts` | Browser client. It calls only `/api/shoes`, `/api/survey`, `/api/quadrant` and `/api/recommend`, and checks the shape of every catalogue and quadrant row it receives. |
| `api/_lib/backend.ts` | Server-only relay helper: backend address, the path allow-list, capped body reading, the upstream request and the status allow-list. The `_lib` prefix keeps it out of routing. |
| `api/shoes/route.ts` | `GET /api/shoes` → the API's `GET /shoes`. |
| `api/survey/route.ts` | `POST /api/survey` → the API's `POST /survey`. |
| `api/quadrant/route.ts` | `GET /api/quadrant` → the API's `GET /quadrant`. |
| `api/recommend/route.ts` | `POST /api/recommend` → the API's `POST /recommend` (W6-3, §4.14). |

#### Relay
- **Scope:** exactly four handlers, one method each, with no catch-all proxy. `/api/docs`, `/api/openapi.json` and `/api/redoc` therefore return 404, and other methods return 405.
- **Path allow-list:** `callBackend` throws, before any request is made, for a path other than `/survey`, `/shoes`, `/quadrant` and `/recommend`. The handler turns the throw into its 502. A FastAPI route added later stays unreachable from the browser until it is listed here.
- **Backend address:** the server-only variable `CRUXUP_API_URL`, read on every request; default `http://127.0.0.1:8000`; trailing slashes removed. It is not a `NEXT_PUBLIC_` variable, so it never reaches the browser bundle.
- **Upstream requests are built fresh:** only `accept: application/json` (plus `content-type: application/json` on `POST`). No incoming header or cookie is forwarded. Requests use `cache: "no-store"`, a 10-second timeout, and `redirect: "error"`.
- **Request body:**
  - `/api/recommend` applies the same JSON check, then reads at most 1 KB (`MAX_RECOMMEND_BODY_BYTES`, 1,024 bytes) and returns 413 `{"errors":["request body exceeds 1024 bytes"]}` beyond it. Survey bodies keep the 64 KiB cap below.
  - The survey handler first requires a JSON content type (`application/json` or `application/*+json`, with optional parameters). Anything else, including no content type, gets 415 `{"errors":["request body must be JSON (content-type: application/json)"]}` without contacting the API.
    - The API itself rejects non-JSON bodies, but the relay always labels the body it forwards as JSON, so the relay has to enforce this.
    - It stops cross-site "simple" requests: a `text/plain` POST from another origin, or an HTML form, is not preflighted by the browser.
    - **No `Origin` or `Sec-Fetch-Site` check is built, and none is needed for CSRF.** A cross-site POST with `application/json` is not a simple request, so the browser sends a CORS preflight first. The route handlers send no CORS headers, so the preflight fails and the request never reaches the handler. Any other content type gets a 415 before any backend call. The check would not stop same-origin XSS, which is the real risk for the survey token (§13).
  - The body is read as a stream with a running byte count, and stops at 65,536 bytes (`MAX_SURVEY_BODY_BYTES`) with a 413 `{"errors":["request body exceeds 65536 bytes"]}`. An oversized `content-length` is refused before reading.
  - The body is forwarded unparsed: every validation rule stays in the Python layer (§4.7, §4.9).
- **Responses:**
  - **Status allow-list.** `relay(upstream, expected, unavailable)` passes the upstream status and body through unchanged only for the statuses the route expects: 201 and 422 for `/survey` (the token, and the API's validation list, which the form interprets); 200 for `/shoes` and `/quadrant`; 200 for `/recommend`. `/api/recommend` maps the API's 404 and 422 to fixed bodies before this check: `{"errors":["survey not found"]}` and `{"errors":["The survey token was not accepted."]}`, with the same statuses.
  - **Masking.** Any other upstream status (the API's 500 and 503, an unexpected 4xx or 2xx) becomes a 502 with a fixed body, and the upstream body is discarded unread. So does a failed upstream call (refused, timed out, redirected, or a path refused by the allow-list). The bodies are `{"errors":["The survey service is unavailable. Please try again later."]}`, `{"errors":["The catalogue service is unavailable. Please try again later."]}`, `{"errors":["The quadrant service is unavailable. Please try again later."]}` and `{"errors":["The results service is unavailable. Please try again later."]}`. Every error from the relay therefore has the API's 422 envelope, `{"errors": [...]}`, and no API error text reaches the browser (`timeline.md` §13, decided 2026-11-05).
  - No handler sets route-segment config. Since Next.js 15, `GET` route handlers are dynamic by default, and `POST` is never cached; the build lists all four as dynamic. Avoiding the `dynamic` export also keeps the handlers valid if Cache Components is ever enabled, since that option removes it.

#### Form
- **Groups:** "Your feet" (width, instep, toe shape, arch, heel, street size), "How you climb" (discipline, terrain, level), "Budget" (cap in US dollars), and "Shoes you know" (the two pickers).
- **Every question is optional.**
  - Each select starts on an empty "Not sure" option, and its option values are the API's vocabularies (§4.7).
  - The number inputs carry the API's bounds as `min`/`max`/`step` (street size 0.1–20 by 0.1; budget 0.01–99,999.99 by 0.01), and their hints state the same bounds in words. The browser's own constraint validation stays on.
- **Payload:**
  - Unset answers are left out entirely, never sent as `null` or `""`. An answer naming only shoes is therefore sent as just the anchor list(s), which the API accepts with every fit and preference field NULL (`timeline.md` §7.1).
  - Numbers are sent as JSON numbers.
- **Not asked:** the comfort-vs-performance goal (W6-4). Without it the server derives `goal_x_target`/`goal_y_target` from discipline, terrain and level alone (§12).
- **Outcomes:**
  - 201 replaces the form with a confirmation (`role="status"`), and focus moves to its heading. The survey token is neither displayed nor stored.
  - 422 opens a `role="alert"` summary headed "Please check your answers.", moves focus to it, and keeps the answers. Each message is shown as plain text, never as markup:
    - **Recognised messages are translated** (`lib/errors.ts`). Today these are the API's two shoe-size errors, which are the only validation errors the form's constraints still allow through. They become plain language that names the shoe. For example, "Size for Scarpa Instinct VSR (unisex): use only letters, numbers, spaces and . / + - (for example 41 or 8.5)." The text is a link that moves focus to that size field. The field is marked `aria-invalid`, and the message is attached through `aria-describedby`; both clear when the field is edited.
    - **Any other message** is shown as "One of your answers could not be accepted. Please check them and try again.", with the API's original text inside a native "Technical details" disclosure.
    - Recognition matches the API's wording. If that wording changes, messages fall back to the generic text rather than being lost.
  - Any other failure shows one general message.
  - While a submission is pending, the button reads "Sending…" and is `aria-disabled` rather than `disabled`, so it keeps focus; repeat submissions are ignored.
- **Catalogue failure:** if the catalogue cannot be loaded, or a row does not match the expected shape, both pickers are disabled and explain why, and each offers a "Try again" button. The rest of the form can still be submitted. The catalogue request is aborted if the page is left before it completes.

#### Anchor picker
- **Pattern:** the WAI-ARIA combobox with a listbox popup, written without a UI library.
  - The input has `role="combobox"`, `aria-expanded`, `aria-controls`, `aria-autocomplete="list"`, `aria-activedescendant` and a `<label>`.
  - Options carry `aria-selected`.
- **Filtering:** client-side and case-insensitive. Every typed word must appear in the shoe's brand, model, version or gender label.
- **Disambiguation:**
  - Each option names the brand, model, version (when there is one) and gender. For example, "Scarpa Instinct VS (unisex)" and "Scarpa Instinct VSR (unisex)", or "La Sportiva Solution (unisex)" and "La Sportiva Solution Comp (unisex)".
  - A chosen shoe is submitted as `{brand, model, version, gender}`, copied from its `GET /shoes` row, plus `size` if one was entered. The API's tests pin that exactly this always resolves to that one shoe (§4.9). The row's `id` is never sent.
- **Keyboard and pointer:**
  - ArrowDown and ArrowUp open the list and move through the options, wrapping at the ends. Enter selects, Escape closes the list or clears the text, and Tab moves on. Clicking the field opens the full list.
  - **Enter in the picker never submits the form.** It chooses the active option, or does nothing. A search query is never an answer, and accidentally submitting the whole questionnaire is costly. The submit button, and Enter in other text fields, still submit.
  - Key handling is suspended during IME composition.
  - The active option is scrolled into view, and is marked by an outline as well as a colour, so it stays visible in forced-colours mode.
  - Pressing on the list's scrollbar does not close it.
  - The hint explains the keys: type to search, then use the arrow keys and Enter.
- **Announcements:** each picker has one visible status line, which is also a polite live region. In priority order it shows:
  - the loading or error message;
  - "… added. N selected." or "… removed. N selected." after a change;
  - "N shoes match" while typing;
  - "No matching shoes." This gains "Shoes you already chose are not shown." whenever choices are being hidden.
- **Chosen shoes** are listed with an optional size field and a "Remove …" button. A shoe already chosen in either list is not offered again.
  - The size field's visible label is "Size (optional)", and its accessible name continues "for <shoe>".
  - Its hint states the accepted format: letters, numbers, spaces and `. / + -` (the fractions ½ ⅓ ⅔ ¼ ¾ are also accepted).
  - Its length limit (64) and accepted punctuation are constants tested against `anchors.py`.

### 4.12 Quadrant chart and table — `frontend/src/app/{quadrant,components,lib}/`

The §3 quadrant as a page (W6-2). The page is static; the data is fetched in the browser from `/api/quadrant` (§4.11). The chart and the table render the same list, so the two views cannot disagree. Paths below are relative to `frontend/src/app/`.

| File | Role |
|---|---|
| `quadrant/page.tsx` | Server component. Title "Shoe quadrant \| CruxUp", an `<h1>`, an intro saying every position is an estimate, and `QuadrantView`. It names no source. |
| `quadrant/QuadrantView.tsx` | Client component. Calls `fetchQuadrant()` on mount with an `AbortController`, as `SurveyForm` does for the catalogue, so an unmount or retry is never shown as an error. One always-mounted status region for loading; on failure, an alert with a fixed plain-language message and a "Try again" button. The chart and the table each sit in a section headed by an `h2`. |
| `components/QuadrantChart.tsx` | Hand-built SVG chart: frame, labels, marks, keyboard model, tooltip, accessible names and legend. No chart library. |
| `components/QuadrantTable.tsx` | The non-visual alternative (below). |
| `lib/quadrant-scale.ts` | `toChartPoint()`: maps `[-1, 1]²` onto a 480-unit square with 72-unit padding, and inverts y. |
| `lib/quadrant-labels.ts` | `QUADRANT_LABEL`: the §3 quadrant names, shared by chart and table. |
| `lib/format-axis-value.ts` | `formatAxisValue()`: two decimals with a true minus sign, never `−0.00`. |

- **Client.** `fetchQuadrant(signal?)` in `lib/api.ts` is shaped like `fetchShoes`: a non-2xx answer, a body that is not a list, or any malformed row throws. Each row must pass `isShoe` and have `x` and `y` numbers in [−1, 1], a known `prior_source` and `quadrant`, and a boolean `is_anchor`.
- **Axes and orientation.** x runs from comfort (−1) to performance (+1). y runs from stiff (−1) to soft (+1), with soft drawn at the top, so Q1 (performance and stiff) sits bottom-right. This follows the §3 axes, not mathematical quadrant numbering, and the scale tests pin it.
- **Encodings.** Provenance is shown by shape and fill, never colour alone: hand-placed is a filled circle, spec-derived a hollow one, and corpus a filled square. The corpus square is reserved, since no corpus rows exist. Marks have radius 5 units, or 7 for an anchor. Only the five §3 anchors carry a direct label. The legend lists only the encodings on the page.
- **Quadrant labels** sit outside the frame, so no point or anchor label can cover one. Each corner label is split over two lines.
- **Text size.** The viewBox is 480 units. Axis, quadrant and anchor text is 18 units, which at the 328 px phone content width (360 px less two 16 px gutters) is about 12.3 px. The figure is capped at `max-w-xl`.
- **Hit areas.** Each point has a transparent circle of radius 20 units, about 27 px across at 328 px, which clears the 24 px target size. Hit areas overlap in dense clusters, so every mark is drawn again in an `aria-hidden` layer above all hit areas, with its own shoe's hover handlers: a pointer on a visible mark always opens that shoe's tooltip. The keyboard reaches every shoe regardless.
- **Keyboard model.** Points are ordered from comfort to performance (by x, then soft before stiff, then name). A roving tabindex keeps one point in the Tab order, the last one focused. Right and Down step to the next point, Left and Up to the previous, Home and End jump to the ends, and nothing wraps. Each point is `role="img"` with `aria-roledescription="shoe"`. A visually hidden instruction on the group describes the order and the Escape key.
- **Accessible names and tooltip.** Both come from one helper, so they say the same thing, for example: "Scarpa Drago (unisex). Comfort–performance 0.80, leaning performance. Stiff–soft 0.85, leaning soft. Hand-placed. Section 3 reference shoe." A value within 0.05 of zero reads "neutral". Shoe names come from `lib/shoe.ts`. The tooltip appears on hover and on focus; Escape, blur, a pointer-down outside the chart, or the pointer leaving both the point and the tooltip hides it. It is `aria-hidden`, since it repeats the accessible name, but it still takes the pointer: it stays open while hovered, and a 300 ms hide delay lets the pointer cross the gap from the point (WCAG 1.4.13, hoverable and dismissible).
- **Target and highlights (W6-3):** an optional `target` draws a crosshair, and `highlightIds` (the top 3 on `/results`) are filled and labelled while the other points are muted (§4.14).
- **Table alternative** (`QuadrantTable`). Visible rather than sr-only, because hover cannot reach overlapping points and touch targets are small. It has one `tbody` per quadrant, headed by a row header, with columns for shoe, comfort–performance, stiff–soft, placement and section-3 reference. An empty quadrant reads "No shoes". Each shoe cell carries a visually hidden quadrant cue, because screen-reader support for row-group headers is uneven. The table sits in a keyboard-reachable region that scrolls horizontally, so the page does not scroll sideways at 375 px.
- **Phone width.** The page pads `p-4` below `sm` and `p-8` above. `e2e/quadrant.spec.ts` asserts no sideways scroll at 375 px.

### 4.13 Scorer — `backend/app/recommend/`

The v0 scorer behind `POST /recommend` (W3-1a and W7-2, `timeline.md` §7, §11). `score.recommend()` is a pure function that ranks one survey's candidate shoes; it does no IO. The route (§4.9) loads the rows, calls it and persists the result. It was built fuller than W3-1a's spec, which ranked by style only: it also assesses Fit and Budget and computes confidence. The user kept it as built on 2026-11-06; each deviation is recorded in `timeline.md` §13. Every weight is judgement-set and nothing is tuned (D8).

| Module | Role | Timeline |
|---|---|---|
| `scorer_config.py` | Every output-affecting constant, `SCORER_VERSION = "v0-slice"`, the Fit_cat tables, `ScoringError` and `check_config()` | §7.2, §7.6, §7.7 |
| `style.py` | The Style term, and `q*` resolution from a stored survey row | §7.3, §7.5 |
| `fit.py` | Fit: the anchor term (Fit_anchor) and the categorical term (Fit_cat), blended by λ | §7.2 |
| `confidence.py` | Confidence from survey completeness, anchors and placement source, with a label | §7.7 |
| `score.py` | `recommend(survey, shoes, size_rows) -> Ranking`: the gates, the combined score and the ranking | §7.6, D9 |

- **Constants.** `check_config()` runs at import and raises `RuntimeError` for a negative weight, weights that do not sum to 1, a value outside [0, 1], table keys that differ from the enum key sets, or misordered label thresholds. `test_scorer_config.py` pins every value, so an output-affecting edit shows in the diff beside `SCORER_VERSION`, which is stored on each `recommendation` row (§5.3).
- **Formulas** (`timeline.md` §7 notation):
  - **Fit** = λ·Fit_anchor + (1−λ)·Fit_cat when both exist, otherwise whichever exists, otherwise the term is dropped. λ = 0.7.
    - **Fit_anchor.** A shoe's family is `(last_shape, downturn)`. Similarity is 1 − (|Δlast| + |Δdownturn|)/4 over 0/1/2 ordinals; a NULL field counts as one step. Good anchors only: the maximum similarity. Bad anchors only: 1 − the maximum. Both: the average of the two.
    - **Fit_cat** is the mean of the answered sub-scores: toe shape against last, foot width against last, and instep against closure. The tables are a domain judgement that **needs climber sign-off (W4'-3)**. `arch` and `heel_fit` are unused: the catalogue has nothing to match them against.
  - **Style** = 1 − ‖q − q\*‖₂ / (2√2), in [0, 1].
  - **Budget** = 1 − price / (2·cap): 1.0 for a free shoe, 0.5 at the cap. A NULL price gets Budget 0.5 when a cap is set (null otherwise, since the term is dropped) and `price_unknown: true` either way, and is never treated as within budget.
  - **Total** = Σ wᵢ·termᵢ / Σ wᵢ over the terms present, with α 0.45, β 0.40, γ 0.15, rounded to 4 dp before ranking.
  - **Gates**, in order, each shoe counted once at the first that drops it: size (`shoe_size_map.size_exists = FALSE` for the survey's street size; the table is empty today, so nothing is dropped), then price (a known price above the cap). Inactive shoes are excluded silently; an active shoe with no prior is counted as `unplaced`.
  - **Confidence** C = (α·c_survey + β·c_place·[q\* known]) / (α+β). c_survey = λ·[anchors resolved] + (1−λ)·(answered of `foot_width`, `toe_shape`, `instep`)/3. c_place is 0.80 for a hand placement and 0.80 × the LOOCV agreement (26/30, §4.3) for a spec one; a corpus placement raises until W3-4 defines it. Labels: high ≥ 0.70, medium ≥ 0.45, low below. Without a target C ≤ 0.53, so such a result is never labelled high (pinned by a test).
- **Target.** The stored `goal_x_target` / `goal_y_target` are used, after validation, when both are present. When both are NULL and a discipline exists, `q*` is recomputed with `target_quadrant(discipline, terrain, level)` and the ranking warns `target_recomputed_without_goal`; since W4'-4a this reaches only rows stored before capture derived `q*`. With no discipline there is no target: Style is dropped, the ranking warns `no_target`, and the shoes are still ranked by Fit and Budget. Exactly one NULL target raises.
- **Term exclusion.** A term with no survey-wide input is dropped and the remaining weights renormalise, so a missing input is neutral rather than zero. Its score is null on every result. With all three dropped, every total is 0.5 and the ranking carries `no_scoring_inputs`.
- **Ordering.** Total descending, then fit descending with null last, then lower-cased brand and model, version, gender and id. Ranks are contiguous from 1. Shoes the user named are ranked by score, never hidden or forced last, and labelled `reported_good_fit` or `reported_poor_fit`.
- **Warnings** are plain strings and never carry a shoe id. Ranking-level: `no_target`, `target_recomputed_without_goal`, `anchor_not_in_catalog:<count>`, `no_scoring_inputs`, and `catalog_field_missing:<field>` when an anchor shoe has a NULL `last_shape` or `downturn`. Per result: `reported_good_fit`, `reported_poor_fit`, `catalog_field_missing:<field>`.
- **Ranking shape** (`RecommendOut`): top level `scorer_version`, `target`, `terms` (`{fit, style, budget}`, whether each term was used), `gated_out` (`{over_budget, size_unavailable, unplaced}`), `warnings`, `results`. Each result has the `QuadrantShoeOut` fields plus `msrp_usd`, `price_unknown`, `fit_score`, `style_score`, `budget_score` (each null when its term is dropped), `total_score`, `confidence`, `confidence_label`, `rank` and `warnings`.
- **Persona fixtures** (`test_recommend_personas.py`, 16 tests) run on the real `shoes.yaml` and change no constant. They are a developer sanity check, **not** W3-1's climber check, which has not been done:
  - sport with an overhang: Solution and Instinct VS above TC Pro, top result in Q1;
  - trad and crack, comfort: TC Pro and Mythos above Drago, Mythos `price_unknown`;
  - beginner with a $120 cap: Origin ($129) and Momentum excluded, every result within the cap or `price_unknown`, Tarantulace in the top three;
  - Solution as a good anchor with a target: it ranks first at fit 1.0. With Solution as the only anchor and no target, 8 shoes tie at fit 1.0 (pinned): last families are coarse;
  - an empty survey: every confidence is low.
- **Unit tests:** `test_score.py` (75), `test_fit.py` (47), `test_style.py` (21), `test_confidence.py` (33), `test_scorer_config.py` (19). Known gaps are in §12.
- **Known availability limit: one corrupt active catalogue row fails every request.** The scorer does not skip a bad row: a `corpus` prior (until W3-4), an on-axis prior or an unknown `last_shape` (once Fit is scored) raises, so every `POST /recommend` is the masked 500 until the row is fixed. This is deliberate, since skipping would hide a catalogue bug and change rankings silently, and it is pinned by `test_recommend_one_bad_active_shoe_fails_the_whole_request_loudly`. `validate.py` and the seed are meant to be the guard, but today only the on-axis prior is rejected there: `prior_source: corpus` passes both `validate.py` and the schema CHECK, and `last_shape` has no rule in either (§12).
- **c_survey feeds C only.** §7.2 has a survey-fit confidence discounting Fit; as built, c_survey enters the confidence C and does not discount the Fit score (`timeline.md` §13).

### 4.14 Results page — `frontend/src/app/{results,api}/`

The ranked results page (W6-3, `timeline.md` §11 and §13). It reads the survey token the questionnaire left behind, asks the API for the ranking through its own route handler, and renders the result. The token handoff is a decision of 2026-11-06, not the HttpOnly cookie that v3.3 specified.

- **Token handoff.** `SurveyForm` stores `survey_token` under `SURVEY_TOKEN_KEY` (`cruxup.surveyToken`) in `sessionStorage`, then calls `router.push("/results")`. If storage is blocked, the answers are still saved and the results page offers the survey again. The token is never in a URL.
- **Reading the token.** `ResultsView` reads it with `useSyncExternalStore`. The server render and hydration see `null` (unknown), so nothing flashes before the client reads storage. An empty string means no survey was taken.
- **Route handler `POST /api/recommend`** (`api/recommend/route.ts`). It requires a JSON content type, reads at most 1 KB, forwards the raw body to `/recommend` through `callBackend`, and returns fixed `{"errors": [...]}` bodies for 404 and 422. Any other status, or a failed call, becomes a masked 502, so no upstream text reaches the browser.
- **Client `fetchRecommendations(token, signal)`.** A 404 or 422 is `survey-not-found`. Any other non-OK status throws. A 200 body must pass `isRecommendResponse`: `price_unknown` agrees with `msrp_usd`, unit scores are in range, ranks run 1..n, ids are unique, and the confidence label is known. A malformed body is an error, never a partial render.
- **States.** `ResultsView` has loading, ready, not-found and failed. Not-found covers a missing token and a 404; it clears the stored token, so a reload does not repeat the request. Failed shows a retry button and moves focus to its alert. A ready response with no results says that no shoes matched and lists the gated-out counts. The not-found message takes focus. The status region stays mounted, so assistive technology keeps announcing changes.
- **Ready view.** The notes (warnings, gated-out counts and unknown prices, from `lib/recommendation-copy.ts`), a key to the three confidence labels, the ranked `ResultCard`s, and the quadrant. Each card is an `<article>` named by its heading and shows its confidence as text. A low-confidence card has a dashed `--warning` border and a rough-starting-point line. A shoe with no price says "Price unknown". A term the scorer dropped reads "Not used", with its reason. The `--warning` token already existed in `globals.css`; it is light-only, like the other tokens.
- **Chart.** `QuadrantChart` receives the ranked shoes, the target (omitted when null) and the top 3 as `highlightIds`. The top 3 are filled in the accent colour and labelled; the rest are muted. A highlighted label goes on the roomier side of its point. The figure is capped at `max-w-sm`, because only a few shoes are labelled. The target never takes the pointer, and the tooltip stays open while hovered (§4.12).
- **Copy.** The page intro says the ranking is a suggestion, that placements are estimates, and that the fit rules have not yet been checked by climbers.
- **Tests.** `results/ResultsView.test.tsx` (39 tests), `ResultCard.test.tsx`, `page.test.tsx`, `routes.test.ts` for the route handler, and `e2e/results.spec.ts` (11 journeys). The journeys run against the mock API's `recommend.json` fixture, and the token `e2e-expired-token` gets a 404.

---

## 5. Data model (PostgreSQL)

Defined in `backend/app/db/migrations/0001_init.sql` and reversed by `0001_init_down.sql`. It requires the `pgcrypto` extension (`gen_random_uuid()`) and targets PostgreSQL 14+; it is verified on 16.15. Only the **product** schema exists; the corpus schema (`corpus_snapshot`, `mention`, `extraction`, `shoe_axis_score`, `lexicon`, `gearlab_label`) is specified in `timeline.md` §8.2 but not implemented.

```mermaid
erDiagram
  shoe ||--o{ shoe_alias : "has (cascade)"
  shoe ||--o{ shoe_size_map : "has (cascade)"
  shoe ||--o{ recommendation : "is recommended in"
  user_survey ||--o{ recommendation : "produces (cascade)"

  shoe {
    uuid id PK
    text brand
    text model
    text version "empty string, never NULL"
    text gender
    text last_shape
    text downturn
    text stiffness_spec
    text closure
    text rubber
    numeric msrp_usd "7,2"
    text status
    numeric quadrant_x_prior "4,3"
    numeric quadrant_y_prior "4,3"
    text prior_source
    timestamptz created_at
  }
  shoe_alias {
    uuid shoe_id FK
    text alias
  }
  shoe_size_map {
    uuid shoe_id FK
    text brand_size
    numeric us_street_equiv "4,1"
    text downsize_note
    boolean size_exists
    text source_url
  }
  user_survey {
    uuid id PK
    text survey_token UK
    text foot_width
    text instep
    text toe_shape
    text arch
    text heel_fit
    numeric street_size
    jsonb known_good_shoes
    jsonb known_bad_shoes
    text discipline
    text terrain
    text level
    numeric goal_x_target
    numeric goal_y_target
    numeric budget_cap_usd
    timestamptz created_at
  }
  recommendation {
    uuid id PK
    uuid survey_id FK
    uuid shoe_id FK
    numeric fit_score
    numeric style_score
    numeric budget_score
    numeric total_score
    numeric confidence
    int rank
    text scorer_version
    boolean accepted
    numeric satisfaction
    boolean returned
    timestamptz feedback_at
    timestamptz created_at
  }
```

### 5.1 Constraints
| Table | Constraint | Enforces |
|---|---|---|
| `shoe` | `shoe_unique_identity` | unique `(brand, model, version, gender)` |
| `shoe` | `shoe_status_valid` | `status` ∈ active, discontinued, revised |
| `shoe` | `shoe_gender_valid` | `gender` ∈ mens, womens, unisex |
| `shoe` | `shoe_downturn_valid` | `downturn` ∈ flat, moderate, aggressive (or NULL) |
| `shoe` | `shoe_closure_valid` | `closure` ∈ lace, velcro, slipper (or NULL) |
| `shoe` | `shoe_prior_x_range`, `shoe_prior_y_range` | priors within `[-1,1]` |
| `shoe` | `shoe_prior_paired` | x and y priors both set or both NULL |
| `shoe` | `shoe_prior_source_valid` | `prior_source` ∈ corpus, hand, spec (or NULL) |
| `shoe` | `shoe_prior_source_paired` | a placement has a source, and a source has a placement |
| `shoe_alias` | primary key `(shoe_id, alias)` + unique index `shoe_alias_globally_unique` on `lower(alias)` | an alias identifies exactly one shoe, case-insensitively |
| `shoe_size_map` | primary key `(shoe_id, brand_size)` | one row per brand size |
| `user_survey` | `survey_token` unique | the only respondent identity |
| `user_survey` | `survey_width_valid`, `survey_instep_valid`, `survey_toe_valid`, `survey_arch_valid`, `survey_disc_valid` | controlled vocabularies |
| `user_survey` | `survey_target_x`, `survey_target_y` | target within `[-1,1]` |
| `user_survey` | `survey_anchors_array` | both anchor columns are JSON arrays |
| `recommendation` | `rec_unique_shoe_per_survey` | a shoe appears once per survey |
| `recommendation` | `rec_rank_positive` | `rank > 0` |
| `recommendation` | `rec_confidence_unit` | confidence within `[0,1]` |
| `recommendation` | `rec_satisfaction` | satisfaction within 1–5 |
| `recommendation` | `rec_feedback_timestamped` | any feedback field requires `feedback_at` |

### 5.2 Indexes
- `shoe_status_idx` — partial, `WHERE status = 'active'`
- `shoe_brand_idx`
- `shoe_size_map_street_idx` — partial, `WHERE size_exists`
- `user_survey_created_idx` — on `created_at DESC`
- `recommendation_survey_rank_idx` — on `(survey_id, rank)`
- `recommendation_feedback_idx` — partial, `WHERE feedback_at IS NOT NULL`

### 5.3 Design notes
- **Privacy:** no personal identifiers are stored. `user_survey.survey_token` is an anonymous handle that links follow-up feedback to recommendations. The schema has no image or biometric storage (D4).
- **`size_exists`** is the only hard sizing gate: it is FALSE only when a brand does not make that size. A downsizing mismatch is intended as a ranked warning, never an exclusion (D9).
- **`scorer_version`** records which weight configuration produced a recommendation, so historical rows stay interpretable after scoring changes.
- **The feedback columns** (`accepted`, `satisfaction`, `returned`, `feedback_at`) exist from the first migration, so online evaluation data is never lost to a later schema change.

---

## 6. Data flows

### 6.1 Loading the catalogue
1. `seed.py` resolves `DATABASE_URL` from `--database-url`, the environment, or `.env`.
2. `load_catalog()` runs `validate()`; any error aborts before a database connection is opened.
3. `seed()` upserts all shoes, clears their aliases in one statement, re-inserts the aliases, and commits — or rolls back under `--dry-run`.

### 6.2 Producing placements
1. **Hand placement:** a person sets `quadrant_x_prior`, `quadrant_y_prior` and `prior_source: hand` in `shoes.yaml`. These rows form the calibration set.
2. **Spec placement** (intended use): for a new shoe with only spec fields, `derive_prior()` supplies the coordinates and the shoe is recorded with `prior_source: spec`.
3. **Refitting:** when hand placements change, `priors.py --refit` refits on rows whose `prior_source` is `hand` and prints new weights. The test suite fails if the checked-in weights drift from `refit()` output or the LOOCV score regresses.
4. **Corpus placement** (planned): aggregated extracted signals would replace placements, with `prior_source: corpus`, for shoes with enough mentions.

### 6.3 Collecting corpus documents (implemented; no source currently cleared)
1. `main()` loads `.env`, opens the landing store and the persistent `QuotaLedger`, and checks the author key — exiting before any request if the key is invalid.
2. For each available source and query: reserve quota → request → hash authors → `INSERT OR IGNORE` the documents → record the run.
3. On quota exhaustion, the source returns partial results and collection moves on.

### 6.4 Capturing a survey
Two entry points share one path: `POST /survey` (§4.9) and the `store.py` CLI.
The questionnaire (§4.11) reaches `POST /survey` through its route handler. It
fills its anchor picker from `GET /shoes`, also relayed, and submits each
chosen shoe as `{brand, model, version, gender}`.
1. `schema.validate()` checks scalar fields and shape without the catalogue. The
   CLI runs it before opening a connection, so an invalid file is rejected
   offline. The API runs it inside `build_survey_row()`, together with step 2.
2. `anchors.resolve_anchors()` resolves each anchor to a `shoe.id` against the
   catalogue, or reports an unknown, ambiguous or contradictory entry.
3. Both error lists are merged, so a caller sees every problem in one round trip.
   The API returns them as a 422 without writing anything.
4. A `survey_token` is generated and the row is inserted in one transaction.
   `--dry-run` exercises the whole path, including JSONB adaptation, then rolls back.
5. The API returns only the `survey_token` (201). It is the sole handle on the row.

`goal_x_target` / `goal_y_target` are never taken from the caller:
`build_survey_row()` derives them with `preferences.target_quadrant()` (§4.8)
from discipline, terrain, level and an optional raw `goal`, which is then
dropped. A caller-supplied target is a 422.

### 6.5 Recommendation (implemented in the API, W7-2)
1. `POST /recommend` (§4.9) locks the survey row and reads every shoe and the survey's street-size rows, on one connection.
2. `score.recommend()` (§4.13) reads the stored `q*` (§6.4), applies the size and price gates, and for each active, placed shoe computes Fit, Style and Budget and their weighted total. A term with no input is dropped and the rest renormalise.
3. Each result gets a confidence from the survey and its `prior_source` (hand 0.80, spec 0.80 × the LOOCV agreement) and a high/medium/low label. Mention count and agreement are not inputs until W3-4.
4. The ranking is upserted as `recommendation` rows under `scorer_version` `v0-slice`; a row that carries feedback is left exactly as it was, and rows no longer ranked are deleted unless they carry feedback. The response is validated, then the transaction commits once.

Not yet implemented: the sizing map (W3-2), corpus-backed confidence and its display contract (W3-4), and learned ranking from feedback (`timeline.md` §13).

---

## 7. Planned components (stubs)

Each stub holds a one-line docstring naming its intended responsibility and task ID. **Several docstrings predate later design decisions; where they conflict, the current design wins:**

| Stub | Docstring intent | Current design (overrides the docstring) |
|---|---|---|
| `db/client.py` | Supabase/Postgres client | Implemented code uses `psycopg` directly against `DATABASE_URL`, which keeps the database portable |
| `db/models.py` | Typed models mirroring migrations; cites "PROJECT_PLAN §8" | That file does not exist; the schema of record is `timeline.md` §8 and `0001_init.sql` |
| `catalog/sizing.py` | "Hard gate in scoring" | **Superseded by D9** — a downsizing mismatch is a warning; only `size_exists` excludes |
| `eval/gearlab_map.py` | "Tune weights to confirmed placements" | **Superseded by D8** — weights are frozen before measurement; evaluation uses LOOCV |
| `eval/metrics.py`, `calibrate.py` | MAE, confusion matrix, calibration | Calibration must beat the `priors.py` baseline to justify the pipeline |
| `nlp/extract.py` | LLM extraction "gated by lexicon" | Whether a lexicon is used at all depends on an experiment (W2-0) |
| `nlp/aggregate.py` | Aggregation with an N_min gate | N_min must come from a measured coverage curve; early data showed 0 of 30 shoes reaching 25 mentions |
| `nlp/train.py` | Distillation | Deferred (D1) |
| `nlp/lexicon/loader.py`, `lexicon.yaml` | Versioned phrase → axis lexicon | Conditional on W2-0 |
| `scraping/sources.py`, `youtube.py`, `reddit.py` | Separate source modules | Sources are implemented inside `collector.py`. YouTube collection is not cleared (`timeline.md` §10.2) |
| `scraping/rate_limiter.py` | Shared token bucket + backoff | Per-source quota is handled by `QuotaLedger`; a shared limiter and backoff remain planned (W0-3) |
| `scraping/compile.py` | Ingest → normalise → snapshot | Planned (W1-full) |
| `scraping/mentions.py` | Mention detection "via shoe_alias / NER" | **Redesign required:** most comments do not name a shoe, so attribution must come mainly from the video or thread subject, with aliases secondary (W1-3) |

---

## 8. Architectural decisions

The decisions that shape the structure, in brief. Full rationale is in `timeline.md` §2.

- **Placement provenance is first-class** (D12). Coordinates never exist without their source; both the catalogue validator and the database enforce it.
- **Product before pipeline** (D7). The first release depends only on the catalogue, the survey and the scorer, not on any corpus. This isolates the product from the unresolved data-access question.
- **Spec-derived placement instead of a capped catalogue** (D12, superseding D6). The catalogue grows through a fitted spec model rather than being limited to what can be hand-placed. Fit and Budget never depend on the corpus.
- **Offline batch extraction, not query-time retrieval.** Any NLP signal is computed ahead of time and stored as placements, so recommendations stay reproducible and fast with no model in the request path. This is not a RAG system.
- **Evaluation discipline** (D8). Calibration weights are frozen before measurement, and small samples use leave-one-out cross-validation.
- **Soft sizing** (D9). A shoe is excluded only for a size its brand does not make.
- **Source-agnostic collection** (D11). No single data source is load-bearing; sources are pluggable adapters that may be unavailable.
- **Non-commercial and advertising-free** (D11). The product carries no advertising. Using free API tiers under non-commercial terms constrains future monetisation for as long as that data is in use.
- **Privacy by construction** (D4). No images, no biometrics, no personal identifiers; author identity exists only as a keyed pseudonym.
- **`q*` has a single author** (decided 2026-10-02, `timeline.md` v3.3). The survey layer computes the user's target when a survey is saved and stores it with the raw answers and a mapping version. Clients cannot supply it, and the scorer reads it (except for rows stored before W4'-4a, which it recomputes without the goal, §4.13). One author means a survey's target never shifts silently when the mapping constants change, and a stored target can always be audited against its inputs. *(Partly built: capture derives `q*` and refuses client targets (W4'-4a, part); the raw answer and mapping version wait for the rest of W4'-4a and W4'-4b.)*
- **The first results are a style match** (decided 2026-10-02). The v0 scorer ranks by quadrant proximity only, and labels fit and budget as not assessed rather than inventing them. Results are written once, so later feedback (§9.4) stays tied to what each user actually saw. **Superseded in part on 2026-11-06** (`timeline.md` §13): the scorer as built also assesses Fit (anchor families plus a judgement Fit_cat table pending climber sign-off) and Budget, computes confidence, and upserts its rows on re-request; a row with feedback is frozen, so feedback still stays tied to what the user saw (§4.9). The user kept it as built. *(Built: W3-1a, W7-2; the results page is W6-3.)*
- **The browser never reaches the service layer directly** (decided 2026-09-21, `timeline.md` §6). The data path is browser → Next.js route handler → FastAPI on localhost → PostgreSQL. Both ends are implemented: FastAPI without CORS middleware (§4.9), and four Next.js route handlers that relay server-side (§4.11). The frontend talks only to its own origin, so there is no CORS surface and the backend is not addressable from the client. The alternative — querying PostgreSQL from TypeScript — was rejected because it would duplicate the anchor resolution, allow-lists and domain guards that already exist and are tested in Python, leaving two validators to keep in step.

---

## 9. Cross-cutting concerns

### 9.1 Security and privacy
- **Secrets** come only from the environment or a gitignored `.env`; `.env.example` holds names only. The loader never returns or logs values.
- **Author pseudonymisation** is keyed and fails closed (§4.6).
- **Survey data** holds no direct identifiers (§5.3).
- **HTTP surface** (§4.9):
  - **Inputs:** `POST /survey` takes only a body, and every rule applied to it
    is the survey layer's. A caller cannot supply `survey_token` or `shoe_id`
    (§4.7).
  - **Queries:** all SQL is parameterised. `GET /shoes` and `GET /quadrant` run fixed queries.
  - **`POST /recommend`** takes only `{"survey_token": <token>}`, matched against
    `[A-Za-z0-9_-]{1,64}` before any connection opens. The token is a bound
    parameter and appears in no SQL text, response or log line; the 404 and 422
    bodies are fixed. Each call writes: it commits `recommendation` rows for the
    survey (§6.5). Anyone holding a token can trigger that write. The token stays out of URLs and
    logs, but a script on the origin can read it from `sessionStorage` (§13, 2026-11-06). An `Origin` check would not change that (§4.11).
  - **Responses:** 201 returns only the token. 5xx bodies are fixed strings.
    The log never records a payload, DSN or exception message.
  - **Error text quotes input.** 422 messages quote submitted values such as
    anchor brand and model. The frontend must render them as text, never as
    markup.
- **Exposure:** the API binds to localhost and has no authentication, because
  the survey is anonymous by design. The Next.js route handlers (§4.11) are the
  only intended client. They forward only `/survey`, `/shoes`, `/quadrant` and `/recommend` (an allow-list in
  `callBackend`), require a JSON content type on every POST (415
  otherwise), cap survey bodies at 64 KiB and recommend bodies at 1 KB, never forward client headers or
  cookies, do not follow redirects, and relay only expected statuses, masking
  every other one as a fixed 502.
- **Before any public deployment** (identified in review, not built):
  - rate limiting at the edge;
  - proxy request and body timeouts;
  - a size cap on relayed API responses (the status allow-list is built, §4.11);
  - security headers (`X-Content-Type-Options`, `Referrer-Policy`, `frame-ancestors` / `X-Frame-Options`) and `poweredByHeader: false` in `next.config.ts`;
  - keeping the API on a private address, so its `/docs` stays unreachable.
- **Frontend rendering:** API error messages are shown only as text, never as
  markup. The questionnaire stores the survey token in `sessionStorage` (§4.14) and never displays it.
- **Git hygiene:** the root `.gitignore` covers `.env`, `.env*.local`, `backend/data/*.sqlite3` (collected third-party content) and `.pytest_cache`. `frontend/.gitignore` covers `node_modules`, `.next`, `next-env.d.ts`, coverage and Playwright output (`test-results/`, `playwright-report/`, `blob-report/`). `frontend/package-lock.json` is committed.
- **Dependency audit:** `npm audit` reports no known vulnerabilities at the pinned versions (§10.2).

### 9.2 External constraints
- **YouTube Data API:** separate daily quota buckets (§4.6). The Developer Policies limit stored data to 30 days and prohibit aggregating data or deriving new metrics from it, so YouTube collection is **not cleared** for the planned aggregation (`timeline.md` §10.2).
- **Reddit Data API:** the free tier is non-commercial, and new OAuth clients need manual approval. Not integrated.
- **Community forums:** terms and `robots.txt` not yet reviewed. Not integrated.
- **GearLab:** planned for internal calibration only, by manual transcription, and never surfaced in the product (D2).

### 9.3 Reliability and idempotency
- **Catalogue load:** idempotent upsert with stable UUIDs; alias replacement that doesn't depend on order; a single transaction.
- **Recommendation:** `POST /recommend` is idempotent for an unchanged survey and catalogue: it upserts on `(survey_id, shoe_id)`, never updates a row that carries feedback, and commits once (§4.9).
- **Collection:**
  - document inserts are idempotent
  - quota is reserved atomically, persisted across processes, and consumed by failed requests
  - partial results survive quota exhaustion
  - one failing query or source does not abort a run

### 9.4 Reproducibility
- Prior weights are checked in and can be regenerated with `priors.py --refit`.
- `recommendation.scorer_version` ties each result to a weight configuration. The scorer writes `SCORER_VERSION` (`v0-slice`, §4.13) on every row, and changing any scorer constant means bumping it. A re-request overwrites the scores and version of rows without feedback in place, so their earlier scores are not kept; rows with feedback keep theirs (`timeline.md` §13).
- The migration pair is reversible and can be re-applied.

---

## 10. Dependencies

### 10.1 Python (`backend/requirements.txt`)
| Package | Imported by implemented code | Purpose |
|---|---|---|
| `psycopg[binary]` | Yes — `seed.py`, `survey/store.py`, `api/` | PostgreSQL access |
| `pyyaml` | Yes — `validate.py`, `seed.py`, `priors.py`, tests | Catalogue parsing |
| `numpy` | Yes — `priors.py` (refit only), tests | Model fitting; test dependency |
| `pytest` | Yes — tests | Test runner |
| `fastapi`, `pydantic` | Yes — `main.py`, `api/` | HTTP API (§4.9) |
| `uvicorn[standard]` | Run as the server (`uvicorn app.main:app`); not imported | ASGI server |
| `httpx` | Yes — tests (`fastapi.testclient`) | Test dependency |
| `pydantic-settings` | No | Planned typed settings |
| `supabase` | No | Declared for hosted Postgres; implemented code uses `psycopg` |
| `praw` | No | Planned Reddit adapter |
| `google-api-python-client` | No | Declared for YouTube; the implemented adapter uses stdlib `urllib` |
| `anthropic` | No | Planned LLM extraction |
| `tenacity`, `structlog` | No | Planned retries and structured logging |

- Beyond these, implemented code uses only the standard library, including `argparse`, `dataclasses`, `datetime`, `enum`, `hashlib`, `hmac`, `json`, `logging`, `pathlib`, `sqlite3`, `urllib` and `zoneinfo`.
- `pglast` is an optional development tool for checking DDL without a server, not a runtime dependency.

### 10.2 Frontend (`frontend/package.json`, locked by `frontend/package-lock.json`)
| Package | Locked version | Purpose |
|---|---|---|
| `next` | 16.3.8 (exact pin) | App Router framework |
| `react`, `react-dom` | 19.2.4 (exact pin) | UI runtime |
| `typescript` | 5.9.3 | Type-checking |
| `tailwindcss`, `@tailwindcss/postcss` | 4.3.3 | Styling, via PostCSS |
| `eslint`, `eslint-config-next` | 9.39.5, 16.3.8 (exact pin) | Lint |
| `vitest`, `@vitest/coverage-v8` | 4.1.11 | Component-test runner; V8 coverage (`npm run test:coverage`, no thresholds yet) |
| `@vitejs/plugin-react` | 6.1.1 | JSX transform for Vitest |
| `jsdom` | 30.1.1 | DOM environment for component tests |
| `@testing-library/react`, `@testing-library/dom`, `@testing-library/jest-dom` | 16.3.3, 10.4.2, 7.0.1 | Component queries and DOM matchers |
| `@playwright/test` | 1.63.0 | End-to-end runner (Chromium) |
| `@testing-library/user-event` | 14.6.7 | Realistic keyboard and pointer input in component tests |
| `@axe-core/playwright` | 4.13.0 (`axe-core` 4.13.0) | Automated WCAG scans in end-to-end tests |
| `@types/node`, `@types/react`, `@types/react-dom` | 20.19.43, 19.3.0, 19.3.0 | Type definitions |

- `next` 16.2.4, the version first scaffolded, falls inside the affected range of published advisories (≤16.3.5), including remote code execution in the Image Optimization API and middleware bypasses. 16.3.8 is outside that range and was the latest release when pinned.
- Vitest is held at 4.x because Vitest 5 requires `@types/node` 22 or later, while the type definitions track the `engines` floor (Node 20).
- Everything listed except `next`, `react` and `react-dom` is a development dependency.

---

## 11. Testing architecture

- **Runners:** `pytest` for the backend, run from the repository root: `python3 -m pytest backend/tests/ -q`. Vitest and Playwright for the frontend (§4.10), run from `frontend/`: `npm test` and `npm run test:e2e`.
- **Frontend tests** (paths under `frontend/`): 449 Vitest tests in 19 files and 35 Playwright tests in 4 files.
  - **`src/app/page.test.tsx`** — 3 Vitest tests. The home page renders a level-1 heading `CruxUp`, a link whose `href` is `/survey`, and a link whose `href` is `/quadrant`. All use role-based queries.
  - **`src/app/survey/page.test.tsx`** — 1 test: the page's metadata title, and that it renders a single `<h1>`.
  - **`src/app/lib/payload.test.ts`** — 8 tests (the eighth checks that chosen shoes keep their order, which the error links rely on):
    - nothing answered gives `{}`;
    - an answer naming only one shoe gives exactly `{known_good_shoes:[{brand, model, version, gender}]}`, with no fit keys and no `null`s;
    - `version: ''` is kept for the base Solution;
    - `size` is included only when it is not empty;
    - selects are sent as strings and numbers as numbers, and blanks are left out;
    - non-finite numbers are left out, and goal keys are never sent;
    - empty anchor lists are left out.
  - **`src/app/lib/vocab.test.ts`** — 9 tests: a **drift guard**.
    - It reads `backend/app/survey/schema.py` and compares `ENUMS`, `PY_ONLY_ENUMS` and the street-size and budget constants with the TypeScript copies, including the derived input bounds.
    - It reads `backend/app/survey/anchors.py` and compares the size field's accepted punctuation, its fractions, and `ANCHOR_SIZE_MAX_LEN`.
    - It fails if parsing finds nothing, so it cannot pass vacuously.
  - **`src/app/lib/errors.test.ts`** — 5 tests: both shoe-size error shapes are translated and tied to the right shoe; unrecognised messages fall back to the generic text, with the original kept for "Technical details".
  - **`src/app/lib/api.test.ts`** — 25 tests: the catalogue loader accepts well-formed rows, rejects six malformed shapes (not an array, a non-string `id`, a missing `brand`, a `null` version, an unknown gender, a `null` row), and passes its abort signal to `fetch`. The quadrant loader requests `/api/quadrant`, accepts the inclusive bounds −1 and 1, rejects ten malformed shapes (among them out-of-range or string coordinates, an unknown `prior_source`, a string `is_anchor` and the API's `ON-AXIS`), rejects a non-2xx answer, and passes its abort signal.
  - **`src/app/lib/quadrant-scale.test.ts`**, **`format-axis-value.test.ts`** — 4 and 3 tests: the corners and centre of the plot, soft drawn above stiff; two decimals, a true minus sign, and no `−0.00`.
  - **`src/app/api/routes.test.ts`** — 48 tests, run in Node, of the relay:
    - exactly GET on `/api/shoes` and `/api/quadrant` and POST on `/api/survey` and `/api/recommend`;
    - `callBackend` refuses `/docs`, `/openapi.json`, `/recommend/`, a trailing slash, a query string and a protocol-relative path without calling `fetch`;
    - non-JSON or missing content types get 415 without contacting the API, and `application/json; charset=utf-8` and `+json` types are forwarded;
    - the backend address is read on every call, with the default when unset;
    - expected statuses pass through with their body (201 and 422 for the survey, 200 for the catalogue and the quadrant); every other status (500, 503, an unexpected 4xx or 2xx) becomes the route's fixed 502 envelope;
    - incoming `cookie` and `authorization` headers are not forwarded;
    - a 413 is returned without contacting the API, both for a false `content-length` and for an oversized one;
    - exactly 65,536 bytes of two-byte characters is forwarded, and one more character is refused;
    - `redirect: "error"` is set;
    - the 502 envelopes are correct.
  - **`src/app/components/AnchorPicker.test.tsx`** — 36 tests:
    - shoes sharing a brand and model get distinct names (Instinct VS/VSR, Solution/Solution Comp, and a test-only pair differing only by gender);
    - keyboard selection submits the right version;
    - arrow keys, Enter (which never submits) and Escape behave correctly, and are ignored during IME composition;
    - `aria-activedescendant` and `aria-expanded` are kept in sync;
    - clicking opens the list;
    - the active option is scrolled into view and carries its outline;
    - the status line's messages appear in the right priority, including the added and removed notices and the "already chosen" explanation;
    - a shoe can be removed by keyboard;
    - shoes already chosen are not offered again;
    - the size field's label, hint, length limit and invalid state are correct;
    - loading, error and "Try again" behave correctly.
  - **`src/app/components/SurveyForm.test.tsx`** — 27 tests:
    - every control is found by its label;
    - pressing Tab from the top reaches every control in order, ending at the submit button;
    - an answer naming only one shoe, made by keyboard, sends exactly that payload;
    - a size error is translated, marks its field invalid, and links to it;
    - an unrecognised 422 keeps `<b>x</b>` as text inside "Technical details";
    - focus moves to the alert;
    - the button reads "Sending…" and a second submit is ignored while pending, then the button is re-enabled;
    - the catalogue request is aborted on unmount;
    - general and catalogue failures, and "Try again", are handled.
  - **`src/app/components/QuadrantChart.test.tsx`** — 61 tests: one point per shoe; quadrant and axis labels placed outside the frame and anchored inside the viewBox; anchors labelled and named as section-3 reference shoes; spec points hollow and hand points filled; provenance and "neutral" in accessible names; the hit area; the legend lists only encodings present; the empty state; the roving tabindex, arrow, Home and End keys; and the tooltip's show and hide paths (focus, hover, mouseleave and pointerleave after the hide delay, outside pointer-down, blur, Escape), that it stays open while the pointer is over it and hides once the pointer leaves it, and its `aria-hidden`.
  - **`src/app/components/QuadrantTable.test.tsx`** — 11 tests: caption, scroll region, one row header per quadrant, Drago in the Q4 group with its sr-only quadrant cue, two-decimal and true-minus values, the anchor flag, and "No shoes".
  - **`src/app/quadrant/QuadrantView.test.tsx`** — 12 tests: the loading status stays mounted and empties; chart and table render after a 200 under `h2`-labelled sections; a 502 or a malformed body shows the plain-language alert; "Try again" recovers; an unmount before the answer logs nothing. **`quadrant/page.test.tsx`** — 1 test: the `<h1>`.
  - **`e2e/home.spec.ts`** — 2 Playwright tests:
    - the home page has the title `CruxUp`, and its link navigates to `/survey`;
    - `GET /survey` returns 200 and shows the questionnaire heading. The URL assertion alone would also pass on a 404, which keeps the same URL.
  - **`e2e/survey.spec.ts`** — 11 Playwright tests, against the mock API:
    - a keyboard-only answer naming only Scarpa Instinct VSR reaches the mock as exactly that payload;
    - a size error reaches the page in plain language, with no internal field paths, and its link focuses the field;
    - an unrecognised 422 stays plain text inside "Technical details";
    - every browser request goes to the app's own origin;
    - an axe WCAG 2 A/AA scan finds no violations in six states (initial; list open; shoe selected; 422 shown; "Technical details" open; confirmation);
    - `/api/docs`, `/api/openapi.json` and `/api/redoc` return 404, and `GET /api/survey` is refused.
  - **`e2e/quadrant.spec.ts`** — 11 Playwright tests, against the mock API's `GET /quadrant`: the home link lands on `/quadrant`; the Q4 label is drawn and the table lists Scarpa Drago under Q4; Tab then ArrowRight shows the second shoe's tooltip; hover shows a tooltip, stays open while the pointer is over it, and Escape hides it; hovering the visible edge of Defy's mark opens Defy's tooltip although Elektra shares its coordinates; no sideways scroll at 375 px; every browser request goes to the app's own origin; and an axe WCAG 2 A/AA scan with a tooltip shown finds no violations.
- **Isolation:** no network and no database. External APIs are replaced by an injected transport; SQLite state uses temporary paths; tests that check availability explicitly remove environment credentials; an autouse fixture supplies a synthetic author key.
- **`backend/tests/test_collector.py`** — 25 tests:
  - privacy: display names never stored; hashes keyed; key read at hash time; weak and compromised keys rejected
  - quota: separate buckets; exhausting one does not block the other; failed requests consume quota; persistence across processes; daily reset; partial results
  - robustness: disabled comments, malformed timestamps, empty bodies, pagination limits
  - storage: idempotent insert, daily volume
  - availability: sources unavailable without credentials
- **`backend/tests/test_priors.py`** — 39 tests:
  - database contract: every derived placement in range and off-axis
  - model behaviour: interaction terms, monotonic stiffness, downturn ordering
  - regression guards: LOOCV score thresholds; checked-in weights equal `refit()` output
  - anchor agreement
  - numpy is imported unconditionally, so the regression guards cannot be silently skipped
- **`backend/tests/test_survey.py`** — 155 tests:
  - schema drift: the five CHECK vocabularies are parsed out of `0001_init.sql`
    and compared, with a self-check so the parser cannot pass vacuously
  - domains: enum membership, numeric range *and* scale, float-noise tolerance
  - anchors: unknown, ambiguous, alias-disambiguated, case-insensitive,
    contradictory, and the optional opaque `size`
  - §7.1: an all-NULL fit profile with anchors alone is accepted, as is an
    entirely empty submission
  - input constraints: oversized and out-of-charset `size`, NUL bytes, lone
    surrogates, anchor-count cap, and a counting catalogue proving a rejected
    oversized submission performs zero lookups
  - persistence: CSPRNG token, parameterised insert, commit/rollback, JSONB
    adaptation
  - CLI: exit codes for malformed JSON, validation failure, missing
    `DATABASE_URL`, and an unreachable database
- **`backend/tests/test_preferences.py`** — 1,334 tests (30 functions, mostly
  parametrised):
  - §7.5 acceptance: each discipline alone lands in its §3 quadrant
  - exhaustive: all 600 combinations of discipline × terrain (4 + omitted) ×
    level (4 + omitted) × `goal` (5 values + omitted) stay inside `[-1, 1]²`, at least
    0.10 from both axes, and in the discipline's quadrant
  - storability: the same 600 outputs pass `schema.validate()`
  - vocabulary pins against `schema.py`, direction of every nudge, monotonic
    `level` and `goal`, and `level`/`goal` leaving `y` unchanged
  - rejections, including `bool`, numeric strings, NaN, ±∞, out-of-range and
    over-large integer `goal`; read-only tables; the import-time invariant check
    fails for bad constants, including under `python -O`
  - golden values with hand-checked arithmetic
- **`backend/tests/test_api.py`** — 156 tests (140 pass and 16 skip without a
  database), through FastAPI's
  `TestClient`. Hermetic tests swap `get_conn` / `get_catalog` for fakes or a
  static catalogue; some keep the real `get_conn` and stub only `psycopg.connect`.
  - wiring: all four routes registered, read from the OpenAPI schema, with
    `/recommend` POST only; no CORS middleware; sync handlers
  - `POST /recommend`, hermetic: a body that is not `{"survey_token": ...}` is
    a 422 with the fixed message that opens no connection and runs no SQL; an
    unknown token is a 404 that never commits; the survey select binds the
    token and locks the row; no SQL text, response or log line contains the
    token; the lock wait is bounded first and a lock timeout is the masked
    503; the upsert never writes a feedback column, and the delete spares
    rows with feedback; a scorer error or a response that fails validation
    never commits; one corrupt active shoe (corpus prior, on-axis prior,
    unknown `last_shape`) is the masked 500 for the whole request; a success
    commits exactly once
  - no validation of its own: a multi-error payload, and a 12-case parity
    table, each assert that the 422 list *equals* `build_survey_row()`'s list
    and that nothing is written. The OpenAPI operation for `/survey` must
    declare no body or parameters, so FastAPI itself validates nothing. `{}`, anchors-only and non-object bodies get
    the survey layer's verdict, not FastAPI's
  - body parsing: malformed JSON, invalid UTF-8, and array or object nesting a
    million deep all yield the one 422 envelope, logged without the body;
    every JSON content type FastAPI parsed is still parsed
  - error hygiene: 503 and 500 bodies never contain a marker planted in the
    exception; `DATABASE_URL` unset gives 503 without a connection attempt;
    a non-database exception gives a JSON 500
  - connection lifecycle: one connection per request, closed exactly once on
    success, validation failure, database error and unexpected error
  - `GET /shoes`: exact keys, `''` versions, string ids, the three shared
    `(brand, model)` pairs, and a round trip — every item resolves back to
    its own `id`
  - `GET /quadrant`: exactly ten keys; `Decimal` priors become floats; each
    quadrant from the sign of x and y; the anchor flag for both Instinct and
    both Solution versions; the `prior_source` literal equals
    `priors.PriorSource`; an on-axis x or y is the masked 500; an empty table;
    no bind parameters; the 503 body never leaks the exception; the connection
    is closed. With a seeded database: the length equals the live count of
    placed shoes, exactly five anchors, each in its §3 quadrant.
- **`backend/tests/test_frontend_contract.py`** — 19 tests. It parses
  `frontend/src/app/lib/types.ts` and asserts that each enum union equals
  `schema.ENUMS` / `PY_ONLY_ENUMS`, `Gender` equals `anchors.GENDERS`,
  `SurveyPayload`'s keys equal `schema.ALLOWED_KEYS` less the two derived
  targets, `AnchorEntry`'s keys equal `ANCHOR_ALLOWED_KEYS`, `Shoe` and
  `QuadrantShoe` match `ShoeOut` and `QuadrantShoeOut`, and `PriorSource` and
  `Quadrant` match the API's literals. Three self-tests keep the parser from
  passing vacuously.
- **Database-backed tests are opt-in by reachability.** Twenty-six tests (ten in
  `test_survey.py`, sixteen in `test_api.py`) use a live PostgreSQL when one is
  available, and skip cleanly when it is not, so the default suite stays
  hermetic.
  - **Every one that writes, except those below,** rolls back and asserts it left `user_survey` empty. The three `GET /quadrant` tests only read.
  - **The exceptions** are `test_api.py`'s `POST /survey` persistence test and
    the eight `/recommend` persistence tests (`test_db_recommend_*`).
    Persistence can only be shown by a real commit, observed from a second
    connection, so they commit and then delete their survey row
    unconditionally; its `recommendation` rows go with it through
    `ON DELETE CASCADE`. The `/recommend` tests need a seeded catalogue.

  CI's check that no `user_survey` rows remain is the backstop. This is the
  project's first automated database coverage; migration apply/reverse remains
  manual for local databases (`SETUP.md` §3).
- **Continuous integration** (`.github/workflows/ci.yml`, GitHub Actions; runs on pushes to `main`, on pull requests, and manually):
  - `unit` — Python 3.10 and 3.12, no database. Validates the catalogue, then runs the suite with an unreachable `DATABASE_URL`, proving the DB-backed tests skip rather than fail.
  - `integration` — a PostgreSQL 16 service container. Applies `0001_init.sql`, reverses it and checks zero tables remain, re-applies it, seeds the catalogue, runs the full suite, and **fails if any test skipped**, since a skip with a database present means the setup broke. It then checks `user_survey` is empty.
  - `frontend` — Node 24, with every `run` step in `frontend/`. Runs `npm ci`, lint, type-check, Vitest with its coverage thresholds (`npm run test:coverage`), `next build`, then installs Chromium and runs Playwright against the production build. The Playwright HTML report is uploaded as an artifact when the job fails.
  - There is no deploy stage, because there is no hosting target.
  - The migration apply/reverse check is automated here; `SETUP.md` §3 remains the manual procedure for a local database.
- **Scorer test files** (§4.13): `test_score.py` (75), `test_fit.py` (47), `test_style.py` (21), `test_confidence.py` (33), `test_scorer_config.py` (19) and `test_recommend_personas.py` (16). None needs a database.
- **Stub test files:** `test_aggregate.py`, `test_calibration.py`.
- **Total:** backend 2,017 passed with a seeded PostgreSQL 16.15, and 1,991 passed plus 26 skipped without one (measured 2026-11-06 on the W6-3 branch). Frontend: 449 Vitest tests and 35 Playwright tests (dev and `CI=1`).

---

## 12. Known gaps and technical debt

- **Survey vocabularies are enforced only in Python.** `heel_fit`, `terrain` and
  `level` have no CHECK constraint in `user_survey`, unlike the five fields beside
  them, so a writer bypassing `survey/schema.py` could store any value. The same
  applies to the `size` length and character-set limits and the anchor count, which
  live in the loading layer rather than the schema. A follow-up migration should
  add the missing constraints.
- **Anchor resolution is one query per anchor.** `PostgresCatalog` issues a lookup
  per entry rather than one batched query. The per-submission cap bounds this, and
  at catalogue scale (30 rows now, ~100 under D12) the cost is negligible, but a
  bulk path would need batching.
- **`lower(brand)`/`lower(model)` matching cannot use an index.** `shoe_brand_idx`
  and `shoe_unique_identity` index the raw columns, so identity resolution is a
  sequential scan. Immaterial at present size; an expression index would be needed
  well past D12.
- **`q*` is derived at capture, but the raw answer is not stored.** The first
  part of W4'-4a (2026-11-05) computes `q*` in `store.build_survey_row()`.
  Clients may no longer send `goal_x_target` / `goal_y_target`; a raw `goal` is
  accepted, converted and dropped. Still open:
  - `user_survey` stores the derived `q*` but neither the raw `goal` nor a
    mapping version, so a stored target cannot be recomputed exactly if the
    mapping constants change. Migration `0002_survey_target` (W4'-4b) adds
    both, plus CHECK constraints that also cover `heel_fit`, `terrain` and
    `level`.
  - The rest of W4'-4a: `schema.DERIVED_FIELDS`, `preferences.MAPPING_VERSION`
    with its fingerprint test, and the per-discipline sweep test.
  - The questionnaire (§4.11) does not ask for the goal until W6-4.
  - The scorer reads the stored `q*`, but for a row stored before W4'-4a (both
    targets NULL, a discipline present) it recomputes `q*` without the goal and
    warns `target_recomputed_without_goal` (§4.13).
- **Two quadrant classifiers.** `catalog/priors.quadrant()` and
  `survey/preferences.quadrant_of()` both label points on the same plane. They
  differ on axis points: the first returns `ON-AXIS`, the second raises. They
  are kept apart because `preferences.py` must not depend on PyYAML.
- **Catalogue size band is stale.** `validate.py` enforces 25–30 shoes, reflecting the superseded D6; the target is now ~100 (D12). It must be raised before the catalogue expands.
- **Refit input filtering in tests.** `test_priors.py` refits on every shoe with coordinates. Once `prior_source: spec` rows exist, it must filter to `hand` rows, as the `--refit` CLI already does, or the model would be fitted partly on its own output.
- **Partial prices.** `msrp_usd` is set on 23 of 30 catalogue rows and null on 7 (§4.1), so budget filtering cannot yet be relied on: `validate.py --require-msrp` fails on those seven. The outstanding spot-checks are listed in `timeline.md` §13, and the W5-1d row stays open until the catalogue expands.
- **Unused declared dependencies:** 7 of 15 packages are declared ahead of use (§10.1).
- **Unpinned dependencies.** `backend/requirements.txt` pins no versions, so CI
  installs the newest releases. Running the suite against them surfaced two
  test breaks that the code itself did not have:
  - FastAPI 0.14x no longer lists included routes in `app.routes`.
  - Python 3.12+ decouples the JSON parser's recursion guard from
    `sys.getrecursionlimit()`.

  The tests now use version-stable checks, but a future release can still break
  CI without a code change.
- **Service-edge controls live in the Next.js route handlers.** The API has no
  request-size limit, leaves `/docs` and `/openapi.json` enabled, and has no
  authentication (§4.9, §9.1). This is safe only while it is reachable solely
  through the relay. The relay forwards only `/survey`, `/shoes`, `/quadrant` and `/recommend`,
  requires JSON, and caps survey bodies at 64 KiB and recommend bodies at 1 KB (§4.11), but **neither layer limits request
  rate**, so nothing stops repeated anonymous submissions. The other controls
  still needed before a public deployment are listed in §9.1.
- **No connection pool.** Each request opens and closes its own connection. At
  current scale that is simpler than a pool; under load, or with multiple
  worker processes, it can approach PostgreSQL's `max_connections`.
- **Scorer gaps (W7-2, `timeline.md` §13).**
  - Fit_cat is a domain judgement and **needs climber sign-off (W4'-3)**; its numbers are not measurements. W3-1's climber check of the ordering has not been done either.
  - Last families are coarse: with Solution as the only anchor and no target, 8 shoes tie at fit 1.0 (pinned by a test), and the tie-break decides their order.
  - No gender filter: mens and womens rows both appear.
  - `arch` and `heel_fit` are collected but unused.
  - A result with no target can never be labelled high (by design, §4.13).
  - No rate limit on `POST /recommend` or `POST /api/survey` in the app. An edge rate limit is a deployment prerequisite (`timeline.md` §13).
  - A row with feedback is frozen: it keeps the rank, scores and `scorer_version` it had when the feedback was given, so its stored rank can collide with or skip the ranks of a later response.
  - Re-requests overwrite the scores and `scorer_version` of rows without feedback in place, so a scorer upgrade loses those earlier scores, and rows do not record the placement used.
  - One corrupt active catalogue row makes every `POST /recommend` a 500 (§4.13). `validate.py` does not reject `prior_source: corpus` or an unknown `last_shape`, and the schema has no CHECK for either.
- **Stale stub docstrings** in `catalog/sizing.py`, `eval/gearlab_map.py`, `scraping/mentions.py` and `db/models.py` contradict the current design (§7).
- **Broken references:** `db/models.py` and `scaffold.sh` cite `PROJECT_PLAN.md`, which does not exist; the plan of record is `timeline.md`.
- **Legacy dead code:** `backend/scraping/` (`compile.py`, `sources.py`, `NLP_training_data.txt`) and `backend/NLP/` (`processing/NLP.py`, `training/trainer.py`) are empty files from an earlier layout, duplicated by `backend/app/`.
- **Module split mismatch:** collection sources live in `collector.py`, but stub modules for a per-source split remain under `backend/app/scraping/`.
- **Migration edited in place:** `0001_init.sql` was changed after first use to add `prior_source`. That is acceptable before any deployment; later changes should be additive migrations.
- **`is_anchor` has no gender in its key.** `GET /quadrant` matches
  `(brand, model, version)` against `validate.ANCHORS`, so a future gendered
  twin of an anchor would be flagged as one too. No such row exists today.
- **Quadrant chart limits.** Overlapping points: hover reaches only the topmost
  one; the keyboard and the table reach every shoe, and points are not jittered,
  by design. Point marks are smaller than 44 px touch targets; their hit areas
  are ≥ 24 px, and the table is the touch path.
- **Colour tokens are light-only and partial.** `globals.css` carries only the
  tokens the quadrant page uses, without dark-mode values; the questionnaire
  still uses Tailwind palette classes. A dark mode needs both to move to tokens
  together.
- **Results page limits (W6-3).** Every ranked shoe is listed: there is no paging and no gender filter (the scorer gap in §4.13). The legend's "Highlighted" label is generic. The chart is capped at `max-w-sm`, so it is small on a phone. No `Origin` check is built; it is not needed for CSRF (§4.11), and it would not stop a script on the origin, which can read the token (`timeline.md` §13).
- **Error translation depends on the API's wording.**
  - The API returns 422 errors as developer-phrased strings, e.g. `known_good_shoes[0]: 'size' contains [','] -- …`.
  - The questionnaire translates the two shoe-size shapes into plain language tied to their field (§4.11) by matching that text. Every other message falls back to generic wording, with the original under "Technical details".
  - This is enough while the form's own constraints let only size errors through. But a reworded API message silently loses its translation, and a new validation rule would surface only as the generic text.
  - Structured errors from the API (a field path and a code per error) would remove the text matching.
- **No manual screen-reader verification.** The quadrant chart's roving tabindex and accessible names were checked with axe and unit tests only. The questionnaire was checked with axe in six states and against the WAI-ARIA combobox pattern by review, but not with NVDA, JAWS, VoiceOver or TalkBack. The live-region announcements and the alert that also takes focus may sound different across screen readers. The forced-colours outline on the active option has been checked by class name only, not rendered.
- **End-to-end tests run against a mock API.** `e2e/mock-api.mjs` validates nothing, and `e2e/fixtures/shoes.json` and `quadrant.json` are snapshots of the catalogue that are not regenerated when the catalogue changes. A change to the real API's contract therefore would not fail the Playwright suite. The relay's behaviour against the real API is covered by the backend's own tests plus a manual end-to-end check; CI does not run one.
- **End-to-end tests use different servers locally and in CI.** Local runs use `next dev` and CI uses `next start`, so behaviour that differs between development and production builds (for example prefetching, or dev-only warnings) can pass in one and fail in the other. CI is the authoritative run. To reproduce it locally, run `npm run build` and then `CI=1 npm run test:e2e` in `frontend/`.
- **A coding-agent environment makes `next dev` write files.** When Next.js 16.3 detects that it is running inside a coding agent (through environment variables such as `AI_AGENT` or `CLAUDECODE`), `next dev` creates `AGENTS.md` and `CLAUDE.md` in its project directory, `frontend/`. If a `CLAUDE.md` already exists there, it inserts its own rules block into it. Neither file is part of the repository, and `next start` and `next build` do not do this.
- **Documentation stubs:** `docs/eval-methodology.md` and `docs/lexicon-guide.md` are placeholders, and `README.md` is a single line.
- **No corpus source is cleared** (§9.2), so the NLP half of the architecture has no permitted input today.

---

## Verification

These commands re-check the mechanically verifiable claims in this document:

```bash
python3 -m pytest backend/tests/ -q                              # 2017 passed with a migrated, seeded database (tests commit and delete rows: use a scratch database)
python3 -m pytest backend/tests/test_collector.py -q             # 25 passed
python3 -m pytest backend/tests/test_priors.py -q                # 86 passed
python3 -m pytest backend/tests/test_survey.py -q                # 168 passed, 10 skipped without a database (178 with one)
python3 -m pytest backend/tests/test_preferences.py -q           # 1334 passed
python3 -m pytest backend/tests/test_api.py -q                   # 140 passed, 16 skipped without a database (156 with one)
python3 -m pytest backend/tests/test_frontend_contract.py -q     # 19 passed
python3 -m pytest backend/tests/test_score.py backend/tests/test_fit.py backend/tests/test_style.py backend/tests/test_confidence.py backend/tests/test_scorer_config.py backend/tests/test_recommend_personas.py -q   # 211 passed
DATABASE_URL=postgresql://localhost:1/nope \
  python3 -m pytest backend/tests/ -q                            # 1991 passed, 26 skipped — the suite is hermetic
(cd backend && uvicorn app.main:app --port 8000) &                # then, in another shell:
curl -s localhost:8000/shoes | python3 -c "import json,sys; print(sorted(json.load(sys.stdin)[0]))"   # ['brand', 'gender', 'id', 'model', 'version']
curl -s localhost:8000/quadrant | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d), sum(r['is_anchor'] for r in d))"   # 30 5 (seeded catalogue)
curl -s -H 'content-type: application/json' -d '{"survey_token":"unknown"}' localhost:8000/recommend   # 404 {"errors": ["survey not found"]}; a token from POST /survey gives the ranking (and writes rows)
curl -s -H 'content-type: application/json' -d '{"email":"x"}' localhost:8000/survey   # 422 {"errors": ["unknown key(s) ['email']: ..."]}
python3 backend/app/catalog/validate.py | tail -1                # catalogue valid
python3 backend/app/catalog/validate.py --require-msrp; echo $?  # exit 1: 7 of 30 shoes have null msrp_usd
python3 backend/app/catalog/priors.py --refit | head -2          # LOOCV  MAE x = 0.139  MAE y = 0.113  agreement = 87%
psql -d <db> -f backend/app/db/migrations/0001_init.sql          # applies clean on an empty database
psql -d <db> -f backend/app/db/migrations/0001_init_down.sql     # reverses to zero tables
CRUXUP_AUTHOR_SALT= python3 backend/app/scraping/collector.py; echo $?   # 2 — refuses to start
cd frontend                                                      # every npm command below runs here
npm ci                                                           # installs exactly what package-lock.json records
npm run lint                                                     # no errors, no warnings
npm run typecheck                                                # clean
npm run test:coverage                                            # 449 passed in 19 files; coverage thresholds met
npm run build                                                    # static: /, /_not-found, /quadrant, /results, /survey; dynamic: /api/quadrant, /api/recommend, /api/shoes, /api/survey
npm run test:e2e                                                 # 35 passed (local, next dev + mock API on :8100)
CI=1 npm run test:e2e                                            # 35 passed (production build, next start) — run after npm run build
npm audit                                                        # found 0 vulnerabilities
```
