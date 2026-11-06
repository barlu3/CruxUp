/**
 * Survey/shoe contract shared with the backend. backend/app/survey/schema.py
 * is the source of truth; backend/tests/test_frontend_contract.py parses the
 * `as const` arrays below and fails if they drift from it.
 */

export interface Shoe {
  id: string;
  brand: string;
  model: string;
  version: string;
  gender: Gender;
}

export const FOOT_WIDTHS = ["narrow", "medium", "wide"] as const;
export const INSTEPS = ["low", "medium", "high"] as const;
export const TOE_SHAPES = ["egyptian", "greek", "roman"] as const;
export const ARCHES = ["low", "medium", "high"] as const;
export const HEEL_FITS = ["narrow", "medium", "wide"] as const;
export const DISCIPLINES = ["boulder", "sport", "trad", "gym"] as const;
export const TERRAINS = ["slab", "vertical", "overhang", "crack"] as const;
export const LEVELS = ["beginner", "intermediate", "advanced", "elite"] as const;
export const GENDERS = ["mens", "womens", "unisex"] as const;

export type FootWidth = (typeof FOOT_WIDTHS)[number];
export type Instep = (typeof INSTEPS)[number];
export type ToeShape = (typeof TOE_SHAPES)[number];
export type Arch = (typeof ARCHES)[number];
export type HeelFit = (typeof HEEL_FITS)[number];
export type Discipline = (typeof DISCIPLINES)[number];
export type Terrain = (typeof TERRAINS)[number];
export type Level = (typeof LEVELS)[number];
export type Gender = (typeof GENDERS)[number];

export const PRIOR_SOURCES = ["corpus", "hand", "spec"] as const;
export const QUADRANTS = ["Q1", "Q2", "Q3", "Q4"] as const;

export type PriorSource = (typeof PRIOR_SOURCES)[number];
export type Quadrant = (typeof QUADRANTS)[number];

export interface QuadrantShoe {
  id: string;
  brand: string;
  model: string;
  version: string;
  gender: Gender;
  x: number;
  y: number;
  prior_source: PriorSource;
  is_anchor: boolean;
  quadrant: Quadrant;
}

export interface AnchorEntry {
  brand: string;
  model: string;
  version?: string;
  gender?: Gender;
  size?: string;
}

// The server derives goal_x_target/goal_y_target from `goal`; clients must not send them.
export const SURVEY_FIELDS = [
  "foot_width",
  "instep",
  "toe_shape",
  "arch",
  "heel_fit",
  "street_size",
  "discipline",
  "terrain",
  "level",
  "goal",
  "budget_cap_usd",
  "known_good_shoes",
  "known_bad_shoes",
] as const satisfies readonly (keyof SurveyPayload)[];

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
  goal?: number;
  budget_cap_usd?: number;
  known_good_shoes?: AnchorEntry[];
  known_bad_shoes?: AnchorEntry[];
  goal_x_target?: never;
  goal_y_target?: never;
}

type RefusedSurveyKey = "goal_x_target" | "goal_y_target";

// Constraint-only: fails to compile if SurveyPayload gains a key SURVEY_FIELDS lacks.
export type AssertSurveyFieldsExhaustive<
  T extends never = Exclude<keyof SurveyPayload, RefusedSurveyKey | (typeof SURVEY_FIELDS)[number]>,
> = T;

export interface SurveyCreated {
  survey_token: string;
}

export interface SurveyErrors {
  errors: string[];
}
