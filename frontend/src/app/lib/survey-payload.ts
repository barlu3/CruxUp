import type {
  AnchorEntry,
  Arch,
  Discipline,
  FootWidth,
  HeelFit,
  Instep,
  Level,
  Shoe,
  SurveyPayload,
  Terrain,
  ToeShape,
} from "./types";

export interface AnchorFormEntry {
  shoe: Shoe;
  size: string;
}

// Selects use "" for unanswered; number inputs yield strings.
export interface SurveyFormState {
  foot_width: FootWidth | "";
  instep: Instep | "";
  toe_shape: ToeShape | "";
  arch: Arch | "";
  heel_fit: HeelFit | "";
  street_size: string;
  discipline: Discipline | "";
  terrain: Terrain | "";
  level: Level | "";
  goal: number | null;
  budget_cap_usd: string;
  goodAnchors: AnchorFormEntry[];
  badAnchors: AnchorFormEntry[];
}

// Range and enum validation stays on the server (schema.py is the source of truth).
export function toSurveyPayload(form: SurveyFormState): SurveyPayload {
  const payload: SurveyPayload = {};

  if (form.foot_width) payload.foot_width = form.foot_width;
  if (form.instep) payload.instep = form.instep;
  if (form.toe_shape) payload.toe_shape = form.toe_shape;
  if (form.arch) payload.arch = form.arch;
  if (form.heel_fit) payload.heel_fit = form.heel_fit;
  if (form.discipline) payload.discipline = form.discipline;
  if (form.terrain) payload.terrain = form.terrain;
  if (form.level) payload.level = form.level;

  const streetSize = toNumber(form.street_size);
  if (streetSize !== undefined) payload.street_size = streetSize;

  const budget = toNumber(form.budget_cap_usd);
  if (budget !== undefined) payload.budget_cap_usd = budget;

  if (form.goal !== null) payload.goal = form.goal;

  if (form.goodAnchors.length > 0) payload.known_good_shoes = form.goodAnchors.map(toAnchor);
  if (form.badAnchors.length > 0) payload.known_bad_shoes = form.badAnchors.map(toAnchor);

  return payload;
}

// A blank number input is "", which Number() would turn into 0; NaN and
// Infinity only arise from unusable input, so all mean "unanswered".
function toNumber(value: string): number | undefined {
  if (value.trim() === "") return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

// version is always sent, even "" for base models, so the server can tell
// "Solution" from "Solution Comp" without guessing.
function toAnchor({ shoe, size }: AnchorFormEntry): AnchorEntry {
  const anchor: AnchorEntry = {
    brand: shoe.brand,
    model: shoe.model,
    version: shoe.version,
    gender: shoe.gender,
  };
  if (size.trim() !== "") anchor.size = size.trim();
  return anchor;
}
