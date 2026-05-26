#!/usr/bin/env bash
# Climbing Shoe Recommender — project scaffold.
# Non-destructive: creates directories and ONLY writes files that do not exist.
# Safe to run on the existing repo. Run from repo root:  bash scaffold.sh
# Workstream IDs ([W#]) and section refs (§) map to PROJECT_PLAN.md.
set -euo pipefail

stub () {              # stub <path>   (content read from heredoc on stdin)
  local path="$1"
  mkdir -p "$(dirname "$path")"
  if [ -e "$path" ]; then
    echo "skip   $path"
  else
    cat > "$path"
    echo "create $path"
  fi
}

keep () { mkdir -p "$1"; [ -e "$1/.gitkeep" ] || : > "$1/.gitkeep"; }

echo "== docs =="
stub docs/ARCHITECTURE.md <<'MD'
# Architecture
Narrated layout of the project. See PROJECT_PLAN.md for tasks/workstreams.
MD
stub docs/lexicon-guide.md <<'MD'
# Lexicon Authoring Guide  [W2-1]
Rules for phrase -> axis patterns. Proprietary asset; version every change.
MD
stub docs/eval-methodology.md <<'MD'
# Eval Methodology  [W0-4]
GearLab -> (x,y) mapping, axis MAE thresholds, quadrant confusion matrix.
MD

echo "== root config =="
stub .env.example <<'ENV'
# Supabase
SUPABASE_URL=
SUPABASE_KEY=
# Reddit (OAuth, free tier = NON-COMMERCIAL only)  [W0-3]
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
REDDIT_USER_AGENT=
# YouTube Data API v3
YOUTUBE_API_KEY=
# LLM extraction  [W2-2]
ANTHROPIC_API_KEY=
ENV

echo "== backend =="
stub backend/requirements.txt <<'REQ'
fastapi
uvicorn[standard]
pydantic
pydantic-settings
psycopg[binary]
supabase
praw
google-api-python-client
anthropic
pyyaml
tenacity
structlog
pytest
REQ

stub backend/app/__init__.py <<'PY'
PY
stub backend/app/main.py <<'PY'
"""FastAPI entrypoint. Mounts api/routes. [api]"""
PY
stub backend/app/config.py <<'PY'
"""Env-backed settings (pydantic-settings)."""
PY

# db  [W0-1]
stub backend/app/db/__init__.py <<'PY'
PY
stub backend/app/db/client.py <<'PY'
"""Supabase/Postgres client. [W0-1]"""
PY
stub backend/app/db/models.py <<'PY'
"""Pydantic/ORM schemas mirroring migrations. [W0-1] (PROJECT_PLAN §8)"""
PY
stub backend/app/db/migrations/0001_init.sql <<'SQL'
-- [W0-1] Initial schema. Authoritative DDL lives in PROJECT_PLAN.md §8.
-- Paste the §8 DDL here, then keep this file as the migration of record.
SQL

# catalog  [W5]
stub backend/app/catalog/__init__.py <<'PY'
PY
stub backend/app/catalog/seed.py <<'PY'
"""[W5-1] Load 50-100 shoes from data/shoes.yaml into `shoe`/`shoe_alias`."""
PY
stub backend/app/catalog/sizing.py <<'PY'
"""[W3-2] Per-brand size map -> us_street_equiv. Hard gate in scoring."""
PY
stub backend/app/catalog/data/shoes.yaml <<'YML'
# [W5-1] Seed catalog. One entry per shoe (brand, model, version, gender,
# last_shape, downturn, stiffness_spec, closure, rubber, msrp_usd, aliases).
YML

# scraping  [W1]
stub backend/app/scraping/__init__.py <<'PY'
PY
stub backend/app/scraping/sources.py <<'PY'
"""[W1-1] Source registry + OAuth config. Free Reddit tier is NON-COMMERCIAL."""
PY
stub backend/app/scraping/reddit.py <<'PY'
"""PRAW client. ~60 QPM practical, 10-min rolling window. Cache aggressively."""
PY
stub backend/app/scraping/youtube.py <<'PY'
"""YouTube Data API v3. Transcript scraping is ToS-gray; verify before scaling."""
PY
stub backend/app/scraping/rate_limiter.py <<'PY'
"""[W0-3] Token-bucket / sliding-window limiter. Exponential backoff on 429."""
PY
stub backend/app/scraping/compile.py <<'PY'
"""[W1-2] Ingest -> normalize -> dedup -> versioned corpus_snapshot."""
PY
stub backend/app/scraping/mentions.py <<'PY'
"""[W1-3] Detect shoe mentions via shoe_alias / NER."""
PY

# nlp  [W2] LLM-first
stub backend/app/nlp/__init__.py <<'PY'
PY
stub backend/app/nlp/lexicon/loader.py <<'PY'
"""Load + version lexicon.yaml. [W2-1]"""
PY
stub backend/app/nlp/lexicon/lexicon.yaml <<'YML'
# [W2-1] Proprietary phrase -> axis patterns (~200-300). VERSION every change.
# Example:
# - pattern: "sensitive on rock"
#   axis: y          # soft
#   polarity: 0.8
YML
stub backend/app/nlp/extract.py <<'PY'
"""[W2-2] LLM extraction: attributes + archetype + experience, gated by lexicon.
Replaces v1 backend/NLP/processing/NLP.py."""
PY
stub backend/app/nlp/aggregate.py <<'PY'
"""[W2-3] Aggregate mentions -> (x,y) with experience/recency weights, N_min gate."""
PY
stub backend/app/nlp/train.py <<'PY'
"""[W2-5] DEFERRED (D1). Distill LLM labels -> small classifier ONLY after labels
accrue and cost justifies. Do not build at MVP. Replaces v1 trainer.py."""
PY

# recommend  [W3]
stub backend/app/recommend/__init__.py <<'PY'
PY
stub backend/app/recommend/fit.py <<'PY'
"""[W3] §7.2 Survey-derived fit: categorical match + anchor shoes (G boost / B penalty)."""
PY
stub backend/app/recommend/style.py <<'PY'
"""[W3] §7.3 Quadrant proximity to user target q*."""
PY
stub backend/app/recommend/score.py <<'PY'
"""[W3] §7.6 Combined: alpha*Fit + beta*Style + gamma*Budget, gated by size & price."""
PY
stub backend/app/recommend/confidence.py <<'PY'
"""[W3] §7.7 Recommendation confidence C_j(c_survey, N_j, agreement)."""
PY

# survey  [W4']
stub backend/app/survey/__init__.py <<'PY'
PY
stub backend/app/survey/schema.py <<'PY'
"""[W4'-1] Fit inputs (width/instep/toe/arch/heel) + anchor sets G,B. No images (D4)."""
PY
stub backend/app/survey/preferences.py <<'PY'
"""[W4'-2] Preference inputs -> target q* (discipline/terrain/level/goal/stiffness)."""
PY

# eval  [W0-4]
stub backend/app/eval/__init__.py <<'PY'
PY
stub backend/app/eval/gearlab_map.py <<'PY'
"""[W0-4] GearLab metrics -> (x,y). Tune weights to confirmed placements."""
PY
stub backend/app/eval/metrics.py <<'PY'
"""[W0-4] Axis MAE + 4x4 quadrant confusion matrix."""
PY
stub backend/app/eval/calibrate.py <<'PY'
"""[W2-4] Calibrate NLP (x,y) against GearLab labels; iterate lexicon."""
PY

# api
stub backend/app/api/__init__.py <<'PY'
PY
stub backend/app/api/routes/__init__.py <<'PY'
PY
stub backend/app/api/routes/survey.py <<'PY'
"""POST /survey -> persist user_survey, derive q*."""
PY
stub backend/app/api/routes/recommend.py <<'PY'
"""POST /recommend -> ranked recommendations + confidence."""
PY
stub backend/app/api/routes/shoes.py <<'PY'
"""GET /shoes, /shoes/{id} -> catalog + quadrant scores."""
PY

# tests
stub backend/tests/test_fit.py <<'PY'
"""[W3] Fit scoring incl. anchor boost/penalty."""
PY
stub backend/tests/test_aggregate.py <<'PY'
"""[W2-3] Aggregation + N_min gate + weighting."""
PY
stub backend/tests/test_calibration.py <<'PY'
"""[W0-4/W2-4] Axis MAE <= threshold; quadrant agreement."""
PY

# data dirs (gitignored content)
keep backend/data/gearlab
keep backend/data/snapshots
keep backend/data/cache

echo "== frontend subdirs (Next.js at root) =="
stub src/app/survey/page.tsx <<'TSX'
export default function SurveyPage() {
  return null; // [W6-1] questionnaire UI
}
TSX
stub src/app/results/page.tsx <<'TSX'
export default function ResultsPage() {
  return null; // [W6-3] ranked results + confidence
}
TSX
keep src/app/components
stub src/app/lib/types.ts <<'TS'
// Shared types mirroring backend models. [W6]
export {};
TS
stub src/app/lib/api.ts <<'TS'
// Backend API client. [W6]
export {};
TS

echo "done."