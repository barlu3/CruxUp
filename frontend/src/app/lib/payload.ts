// Pure builder: form state -> POST /survey body. Unset fields are omitted
// (never null, never ""); every key is optional server-side.

import type { AnchorEntry, Shoe, SurveyPayload } from "./types";
import type { EnumField } from "./vocab";

export interface SelectedAnchor {
  shoe: Shoe;
  size: string;
}

export interface FormState extends Record<EnumField, string> {
  street_size: string;
  budget_cap_usd: string;
  known_good_shoes: SelectedAnchor[];
  known_bad_shoes: SelectedAnchor[];
}

export function emptyFormState(): FormState {
  return {
    foot_width: "",
    instep: "",
    toe_shape: "",
    arch: "",
    heel_fit: "",
    street_size: "",
    discipline: "",
    terrain: "",
    level: "",
    budget_cap_usd: "",
    known_good_shoes: [],
    known_bad_shoes: [],
  };
}

const SELECT_KEYS = [
  "foot_width",
  "instep",
  "toe_shape",
  "arch",
  "heel_fit",
  "discipline",
  "terrain",
  "level",
] as const satisfies readonly EnumField[];

function toAnchor({ shoe, size }: SelectedAnchor): AnchorEntry {
  const entry: AnchorEntry = {
    brand: shoe.brand,
    model: shoe.model,
    version: shoe.version,
    gender: shoe.gender,
  };
  if (size.trim() !== "") entry.size = size;
  return entry;
}

function parseNumber(raw: string): number | undefined {
  if (raw.trim() === "") return undefined;
  const n = Number(raw);
  return Number.isFinite(n) ? n : undefined;
}

export function buildPayload(state: FormState): SurveyPayload {
  // Assembled loosely, then typed once: the select values are checked by the
  // server against the vocabulary, which is the single source of truth.
  const out: Record<string, unknown> = {};
  for (const key of SELECT_KEYS) {
    if (state[key] !== "") out[key] = state[key];
  }
  const street = parseNumber(state.street_size);
  if (street !== undefined) out.street_size = street;
  const budget = parseNumber(state.budget_cap_usd);
  if (budget !== undefined) out.budget_cap_usd = budget;
  if (state.known_good_shoes.length > 0) {
    out.known_good_shoes = state.known_good_shoes.map(toAnchor);
  }
  if (state.known_bad_shoes.length > 0) {
    out.known_bad_shoes = state.known_bad_shoes.map(toAnchor);
  }
  return out as SurveyPayload;
}
