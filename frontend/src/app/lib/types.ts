// Shared types mirroring the backend contract (backend/app/survey/schema.py,
// anchors.py and the GET /shoes, GET /quadrant and POST /recommend responses).
// backend/tests/test_frontend_contract.py parses this file and fails if it
// drifts from them.

export type Gender = "mens" | "womens" | "unisex";

/** One row of GET /shoes. */
export interface Shoe {
  id: string;
  brand: string;
  model: string;
  /** '' for a base model. */
  version: string;
  gender: Gender;
}

export type FootWidth = "narrow" | "medium" | "wide";
export type Instep = "low" | "medium" | "high";
export type ToeShape = "egyptian" | "greek" | "roman";
export type Arch = "low" | "medium" | "high";
export type HeelFit = "narrow" | "medium" | "wide";
export type Discipline = "boulder" | "sport" | "trad" | "gym";
export type Terrain = "slab" | "vertical" | "overhang" | "crack";
export type Level = "beginner" | "intermediate" | "advanced" | "elite";

/** One anchor as submitted: exactly the catalogue's identifying fields. */
export interface AnchorEntry {
  brand: string;
  model: string;
  version: string;
  gender: Gender;
  size?: string;
}

/** POST /survey body. Every key is optional; unset means omitted. */
export interface SurveyPayload {
  foot_width?: FootWidth;
  instep?: Instep;
  toe_shape?: ToeShape;
  arch?: Arch;
  heel_fit?: HeelFit;
  street_size?: number;
  discipline?: Discipline;
  terrain?: Terrain;
  level?: Level;
  budget_cap_usd?: number;
  known_good_shoes?: AnchorEntry[];
  known_bad_shoes?: AnchorEntry[];
}

export type PriorSource = "corpus" | "hand" | "spec";
export type Quadrant = "Q1" | "Q2" | "Q3" | "Q4";

/** One row of GET /quadrant: a shoe placed on the section-3 axes. */
export interface QuadrantShoe {
  id: string;
  brand: string;
  model: string;
  version: string;
  gender: Gender;
  /** Comfort (-1) to performance (+1). */
  x: number;
  /** Stiff (-1) to soft (+1). */
  y: number;
  prior_source: PriorSource;
  /** One of the five section-3 reference shoes. */
  is_anchor: boolean;
  quadrant: Quadrant;
}

export type ConfidenceLabel = "high" | "medium" | "low";

/** One ranked row of POST /recommend: a placed shoe plus its scores. */
export interface Recommendation extends QuadrantShoe {
  /** null when the catalogue has no price; then price_unknown is true. */
  msrp_usd: number | null;
  price_unknown: boolean;
  /** Each term score is null when that term was dropped for the whole survey. */
  fit_score: number | null;
  style_score: number | null;
  budget_score: number | null;
  total_score: number;
  confidence: number;
  confidence_label: ConfidenceLabel;
  /** 1..n in response order. */
  rank: number;
  warnings: string[];
}

// Flat interfaces rather than inline object types: the contract test's key
// parser cannot read nested object literals.
export interface RecommendTarget {
  x: number;
  y: number;
}

/** Which terms fed the score; a dropped term's weight is renormalised away. */
export interface RecommendTerms {
  fit: boolean;
  style: boolean;
  budget: boolean;
}

/** How many active shoes each gate dropped. */
export interface GatedOut {
  over_budget: number;
  size_unavailable: number;
  unplaced: number;
}

/** POST /recommend 200 body. */
export interface RecommendResponse {
  scorer_version: string;
  /** The style target used; null when the survey has none. */
  target: RecommendTarget | null;
  terms: RecommendTerms;
  gated_out: GatedOut;
  warnings: string[];
  results: Recommendation[];
}

export interface SurveyErrorBody {
  errors: string[];
}

export interface SurveyCreatedBody {
  survey_token: string;
}
