-- [W0-1a] Product schema. Authoritative DDL: timeline.md §8.1.
--
-- This is the product half of the data model only. The corpus half
-- (corpus_snapshot, mention, extraction, shoe_axis_score, lexicon) lives in
-- 0002_corpus.sql and is deliberately deferred until W0-0 named a source —
-- see timeline.md D5 and §8.2.
--
-- Postgres 14+. Reversal: 0001_init_down.sql.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- gen_random_uuid()

-- ---------------------------------------------------------------------------
-- Catalog
-- ---------------------------------------------------------------------------

CREATE TABLE shoe (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand            TEXT        NOT NULL,
    model            TEXT        NOT NULL,
    version          TEXT        NOT NULL DEFAULT '',   -- '' not NULL: part of the unique key
    gender           TEXT        NOT NULL DEFAULT 'unisex',
    last_shape       TEXT,
    downturn         TEXT,
    stiffness_spec   TEXT,
    closure          TEXT,
    rubber           TEXT,
    msrp_usd         NUMERIC(7,2),
    status           TEXT        NOT NULL DEFAULT 'active',
    -- Spec-derived / hand-placed quadrant prior. In the thin slice (D7) these
    -- ARE the placement; after W2-3 they become the sub-N_min fallback.
    quadrant_x_prior NUMERIC(4,3),
    quadrant_y_prior NUMERIC(4,3),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT shoe_unique_identity UNIQUE (brand, model, version, gender),
    CONSTRAINT shoe_status_valid    CHECK (status IN ('active', 'discontinued', 'revised')),
    CONSTRAINT shoe_gender_valid    CHECK (gender IN ('mens', 'womens', 'unisex')),
    CONSTRAINT shoe_downturn_valid  CHECK (downturn IS NULL OR downturn IN ('flat', 'moderate', 'aggressive')),
    CONSTRAINT shoe_closure_valid   CHECK (closure  IS NULL OR closure  IN ('lace', 'velcro', 'slipper')),
    -- §3: the quadrant plane is [-1,1]^2. Reject anything off the plane at write time.
    CONSTRAINT shoe_prior_x_range   CHECK (quadrant_x_prior IS NULL OR quadrant_x_prior BETWEEN -1 AND 1),
    CONSTRAINT shoe_prior_y_range   CHECK (quadrant_y_prior IS NULL OR quadrant_y_prior BETWEEN -1 AND 1),
    -- Priors are set as a pair or not at all; one axis alone is always a bug.
    CONSTRAINT shoe_prior_paired    CHECK ((quadrant_x_prior IS NULL) = (quadrant_y_prior IS NULL))
);

CREATE INDEX shoe_status_idx ON shoe (status) WHERE status = 'active';
CREATE INDEX shoe_brand_idx  ON shoe (brand);

COMMENT ON COLUMN shoe.version IS
    'Revision that changes the last, e.g. ''Comp'' for Solution Comp. Empty string, never NULL, so it participates in the unique key.';
COMMENT ON COLUMN shoe.quadrant_x_prior IS
    'Comfort (-1) to performance (+1). See timeline.md section 3.';
COMMENT ON COLUMN shoe.quadrant_y_prior IS
    'Stiff (-1) to soft (+1). See timeline.md section 3.';


CREATE TABLE shoe_alias (
    shoe_id UUID NOT NULL REFERENCES shoe(id) ON DELETE CASCADE,
    alias   TEXT NOT NULL,
    PRIMARY KEY (shoe_id, alias)
);

-- Mention detection (W1-3) resolves free text to a shoe. An alias pointing at
-- two shoes is unresolvable, so forbid it in the schema rather than
-- misattributing at query time. Case-insensitive: "solution" and "Solution"
-- are the same alias.
CREATE UNIQUE INDEX shoe_alias_globally_unique ON shoe_alias (lower(alias));

COMMENT ON TABLE shoe_alias IS
    'Surface forms for mention detection. Globally unique (case-insensitive): an ambiguous alias is a data error, not a runtime branch.';


CREATE TABLE shoe_size_map (
    shoe_id         UUID    NOT NULL REFERENCES shoe(id) ON DELETE CASCADE,
    brand_size      TEXT    NOT NULL,
    us_street_equiv NUMERIC(4,1),
    downsize_note   TEXT,
    -- D9: the ONLY hard gate. TRUE = the brand makes this size. Downsizing
    -- mismatch is a ranked warning in the scorer, never an exclusion.
    size_exists     BOOLEAN NOT NULL DEFAULT TRUE,
    source_url      TEXT,
    PRIMARY KEY (shoe_id, brand_size)
);

CREATE INDEX shoe_size_map_street_idx ON shoe_size_map (us_street_equiv) WHERE size_exists;

COMMENT ON COLUMN shoe_size_map.size_exists IS
    'D9 hard gate: FALSE only when the brand does not make this size at all. Never set FALSE for a downsizing mismatch.';


-- ---------------------------------------------------------------------------
-- User survey (D3 questionnaire; D4 derived values only, no images)
-- ---------------------------------------------------------------------------

CREATE TABLE user_survey (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Anonymous handle. This is the ONLY identity in the schema: it links a
    -- later follow-up back to what was recommended without carrying a person.
    survey_token     TEXT        NOT NULL UNIQUE,

    -- Fit self-report (section 7.1). All optional — 7.1 allows shipping fit v0
    -- on anchors alone, so an all-NULL fit profile is valid input.
    foot_width       TEXT,
    instep           TEXT,
    toe_shape        TEXT,
    arch             TEXT,
    heel_fit         TEXT,
    street_size      NUMERIC(4,1),

    -- Anchor sets: the highest-signal fit input (section 7.1).
    -- Shape: [{"brand": "...", "model": "...", "size": "...", "shoe_id": "..."}]
    known_good_shoes JSONB       NOT NULL DEFAULT '[]'::jsonb,
    known_bad_shoes  JSONB       NOT NULL DEFAULT '[]'::jsonb,

    -- Preference inputs -> q* (section 7.5)
    discipline       TEXT,
    terrain          TEXT,
    level            TEXT,
    goal_x_target    NUMERIC(4,3),
    goal_y_target    NUMERIC(4,3),
    budget_cap_usd   NUMERIC(7,2),

    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT survey_width_valid   CHECK (foot_width IS NULL OR foot_width IN ('narrow', 'medium', 'wide')),
    CONSTRAINT survey_instep_valid  CHECK (instep     IS NULL OR instep     IN ('low', 'medium', 'high')),
    CONSTRAINT survey_toe_valid     CHECK (toe_shape  IS NULL OR toe_shape  IN ('egyptian', 'greek', 'roman')),
    CONSTRAINT survey_arch_valid    CHECK (arch       IS NULL OR arch       IN ('low', 'medium', 'high')),
    CONSTRAINT survey_disc_valid    CHECK (discipline IS NULL OR discipline IN ('boulder', 'sport', 'trad', 'gym')),
    CONSTRAINT survey_target_x      CHECK (goal_x_target IS NULL OR goal_x_target BETWEEN -1 AND 1),
    CONSTRAINT survey_target_y      CHECK (goal_y_target IS NULL OR goal_y_target BETWEEN -1 AND 1),
    CONSTRAINT survey_anchors_array CHECK (
        jsonb_typeof(known_good_shoes) = 'array' AND jsonb_typeof(known_bad_shoes) = 'array'
    )
);

CREATE INDEX user_survey_created_idx ON user_survey (created_at DESC);

COMMENT ON TABLE user_survey IS
    'D4: derived measurements only. No images, no biometric captures, no direct identifiers. survey_token is the sole handle.';


-- ---------------------------------------------------------------------------
-- Recommendations + the feedback loop (section 9.4)
-- ---------------------------------------------------------------------------

CREATE TABLE recommendation (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    survey_id    UUID        NOT NULL REFERENCES user_survey(id) ON DELETE CASCADE,
    shoe_id      UUID        NOT NULL REFERENCES shoe(id),

    fit_score    NUMERIC(5,4),
    style_score  NUMERIC(5,4),
    budget_score NUMERIC(5,4),
    total_score  NUMERIC(5,4),
    confidence   NUMERIC(5,4),
    rank         INT         NOT NULL,

    -- Which weights produced this row. Without it, a scoring change makes
    -- every historical recommendation uninterpretable (7.6: weights live in
    -- config and are expected to move).
    scorer_version TEXT      NOT NULL DEFAULT 'v0',

    -- Section 9.4 online metrics. v2 omitted these; adding them after users
    -- have been through the funnel loses that cohort permanently.
    accepted     BOOLEAN,
    satisfaction NUMERIC(2,1),
    returned     BOOLEAN,
    feedback_at  TIMESTAMPTZ,

    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT rec_unique_shoe_per_survey UNIQUE (survey_id, shoe_id),
    CONSTRAINT rec_rank_positive   CHECK (rank > 0),
    CONSTRAINT rec_confidence_unit CHECK (confidence   IS NULL OR confidence   BETWEEN 0 AND 1),
    CONSTRAINT rec_satisfaction    CHECK (satisfaction IS NULL OR satisfaction BETWEEN 1 AND 5),
    -- Any feedback field set implies a timestamp, so 9.4 can window by date.
    CONSTRAINT rec_feedback_timestamped CHECK (
        (accepted IS NULL AND satisfaction IS NULL AND returned IS NULL)
        OR feedback_at IS NOT NULL
    )
);

CREATE INDEX recommendation_survey_rank_idx ON recommendation (survey_id, rank);
CREATE INDEX recommendation_feedback_idx    ON recommendation (feedback_at) WHERE feedback_at IS NOT NULL;

COMMENT ON COLUMN recommendation.accepted IS
    'Section 9.4 acceptance rate. NULL = no feedback yet, which is not the same as rejected.';

COMMIT;
