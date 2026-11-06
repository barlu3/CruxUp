// Browser client. Calls only this app's own route handlers; the browser never
// talks to the FastAPI backend directly.

import type {
  ConfidenceLabel,
  Gender,
  PriorSource,
  Quadrant,
  QuadrantShoe,
  RecommendResponse,
  Recommendation,
  Shoe,
  SurveyPayload,
} from "./types";

/** sessionStorage key for the survey token handed from /survey to /results. */
export const SURVEY_TOKEN_KEY = "cruxup.surveyToken";

export type SubmitResult =
  | { kind: "created"; surveyToken: string }
  | { kind: "invalid"; errors: string[] }
  | { kind: "failed" };

export type RecommendResult =
  | { kind: "ranked"; ranking: RecommendResponse }
  | { kind: "survey-not-found" };

// Records, not arrays, so tsc rejects a set that misses or invents a member of its union.
const GENDER_SET: Record<Gender, true> = { mens: true, womens: true, unisex: true };
const PRIOR_SOURCE_SET: Record<PriorSource, true> = { corpus: true, hand: true, spec: true };
const QUADRANT_SET: Record<Quadrant, true> = { Q1: true, Q2: true, Q3: true, Q4: true };
const CONFIDENCE_LABEL_SET: Record<ConfidenceLabel, true> = { high: true, medium: true, low: true };

function isShoe(v: unknown): v is Shoe {
  if (typeof v !== "object" || v === null) return false;
  const r = v as Record<string, unknown>;
  return (
    typeof r.id === "string" &&
    typeof r.brand === "string" &&
    typeof r.model === "string" &&
    typeof r.version === "string" &&
    typeof r.gender === "string" &&
    Object.hasOwn(GENDER_SET, r.gender)
  );
}

export async function fetchShoes(signal?: AbortSignal): Promise<Shoe[]> {
  const res = await fetch("/api/shoes", { headers: { accept: "application/json" }, signal });
  if (!res.ok) throw new Error(`catalogue request failed (${res.status})`);
  const body: unknown = await res.json();
  if (!Array.isArray(body)) throw new Error("catalogue response is not a list");
  if (!body.every(isShoe)) throw new Error("catalogue response has a malformed row");
  return body;
}

/** The section-3 plane is [-1, 1] on both axes. */
function isAxisValue(v: unknown): boolean {
  return typeof v === "number" && v >= -1 && v <= 1;
}

function isQuadrantShoe(v: unknown): v is QuadrantShoe {
  if (!isShoe(v)) return false;
  const r = v as unknown as Record<string, unknown>;
  return (
    isAxisValue(r.x) &&
    isAxisValue(r.y) &&
    typeof r.prior_source === "string" &&
    Object.hasOwn(PRIOR_SOURCE_SET, r.prior_source) &&
    typeof r.is_anchor === "boolean" &&
    typeof r.quadrant === "string" &&
    Object.hasOwn(QUADRANT_SET, r.quadrant)
  );
}

export async function fetchQuadrant(signal?: AbortSignal): Promise<QuadrantShoe[]> {
  const res = await fetch("/api/quadrant", { headers: { accept: "application/json" }, signal });
  if (!res.ok) throw new Error(`quadrant request failed (${res.status})`);
  const body: unknown = await res.json();
  if (!Array.isArray(body)) throw new Error("quadrant response is not a list");
  if (!body.every(isQuadrantShoe)) throw new Error("quadrant response has a malformed row");
  return body;
}

/** Scores and confidence lie in [0, 1]. */
function isUnitScore(v: unknown): boolean {
  return typeof v === "number" && v >= 0 && v <= 1;
}

function isNullableUnitScore(v: unknown): boolean {
  return v === null || isUnitScore(v);
}

function isCount(v: unknown): boolean {
  return Number.isInteger(v) && (v as number) >= 0;
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null;
}

function isRecommendation(v: unknown, expectedRank: number): v is Recommendation {
  if (!isQuadrantShoe(v)) return false;
  const r = v as unknown as Record<string, unknown>;
  const price = r.msrp_usd;
  return (
    (price === null || (typeof price === "number" && Number.isFinite(price) && price >= 0)) &&
    r.price_unknown === (price === null) &&
    isNullableUnitScore(r.fit_score) &&
    isNullableUnitScore(r.style_score) &&
    isNullableUnitScore(r.budget_score) &&
    isUnitScore(r.total_score) &&
    isUnitScore(r.confidence) &&
    typeof r.confidence_label === "string" &&
    Object.hasOwn(CONFIDENCE_LABEL_SET, r.confidence_label) &&
    r.rank === expectedRank &&
    isStringArray(r.warnings)
  );
}

function isRecommendResponse(v: unknown): v is RecommendResponse {
  if (!isRecord(v)) return false;
  const { target, terms, gated_out: gatedOut, results } = v;
  return (
    typeof v.scorer_version === "string" &&
    (target === null || (isRecord(target) && isAxisValue(target.x) && isAxisValue(target.y))) &&
    isRecord(terms) &&
    typeof terms.fit === "boolean" &&
    typeof terms.style === "boolean" &&
    typeof terms.budget === "boolean" &&
    isRecord(gatedOut) &&
    isCount(gatedOut.over_budget) &&
    isCount(gatedOut.size_unavailable) &&
    isCount(gatedOut.unplaced) &&
    isStringArray(v.warnings) &&
    Array.isArray(results) &&
    // The ordered list and the top-3 highlight rely on ranks 1..n in array order.
    results.every((row, i) => isRecommendation(row, i + 1)) &&
    new Set(results.map((row: Recommendation) => row.id)).size === results.length
  );
}

/**
 * POST the token in the body, never the URL. 404 and 422 both mean the stored
 * token can never match a survey, so the caller should drop it.
 */
export async function fetchRecommendations(
  surveyToken: string,
  signal?: AbortSignal,
): Promise<RecommendResult> {
  const res = await fetch("/api/recommend", {
    method: "POST",
    headers: { "content-type": "application/json", accept: "application/json" },
    body: JSON.stringify({ survey_token: surveyToken }),
    signal,
  });
  if (res.status === 404 || res.status === 422) {
    await res.body?.cancel();
    return { kind: "survey-not-found" };
  }
  if (!res.ok) throw new Error(`recommend request failed (${res.status})`);
  const body: unknown = await res.json();
  if (!isRecommendResponse(body)) throw new Error("recommend response is malformed");
  return { kind: "ranked", ranking: body };
}

function isStringArray(v: unknown): v is string[] {
  return Array.isArray(v) && v.every((s) => typeof s === "string");
}

export async function submitSurvey(payload: SurveyPayload): Promise<SubmitResult> {
  try {
    const res = await fetch("/api/survey", {
      method: "POST",
      headers: { "content-type": "application/json", accept: "application/json" },
      body: JSON.stringify(payload),
    });
    if (res.status === 201) {
      const body: unknown = await res.json();
      const token = isRecord(body) ? body.survey_token : undefined;
      // A 201 without a usable token cannot lead to results, so it is a failure.
      if (typeof token === "string" && token !== "") return { kind: "created", surveyToken: token };
      return { kind: "failed" };
    }
    if (res.status === 422) {
      const body: unknown = await res.json().catch(() => null);
      const errors = (body as { errors?: unknown } | null)?.errors;
      if (isStringArray(errors) && errors.length > 0) return { kind: "invalid", errors };
    }
    return { kind: "failed" };
  } catch {
    return { kind: "failed" };
  }
}
