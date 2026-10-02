// Shared types mirroring the backend contract (backend/app/survey/schema.py,
// anchors.py and the GET /shoes response).

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

export interface SurveyErrorBody {
  errors: string[];
}

export interface SurveyCreatedBody {
  survey_token: string;
}
