import {
  CONFIDENCE_LABELS,
  GENDERS,
  PRIOR_SOURCES,
  QUADRANTS,
  type ConfidenceLabel,
  type Gender,
  type PriorSource,
  type Quadrant,
  type QuadrantShoe,
  type Recommendation,
  type RecommendResponse,
  type Shoe,
  type SurveyPayload,
} from "./types";

/**
 * unavailable: network failure or 502/503, retrying later may work.
 * timeout: 504, the backend was too slow.
 * rejected: 400/413/415, the request itself was refused; retrying is pointless.
 * bad_response: the reply was not the shape this client expects.
 */
export type ApiErrorCode = "unavailable" | "timeout" | "rejected" | "bad_response";

export type SubmitSurveyResult =
  | { ok: true; surveyToken: string }
  | { ok: false; errors: string[] };

export class ApiError extends Error {
  readonly code: ApiErrorCode;

  constructor(code: ApiErrorCode, message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "ApiError";
    this.code = code;
  }
}

const FALLBACK_MESSAGES: Record<ApiErrorCode, string> = {
  unavailable: "The service is temporarily unavailable.",
  timeout: "The service took too long to respond.",
  rejected: "The request was rejected.",
  bad_response: "The service returned an unexpected response.",
};

export async function submitSurvey(payload: SurveyPayload): Promise<SubmitSurveyResult> {
  const response = await request("/api/survey", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (response.status === 201) {
    const body = await readJson(response);
    if (isRecord(body) && typeof body.survey_token === "string") {
      return { ok: true, surveyToken: body.survey_token };
    }
    throw new ApiError("bad_response", FALLBACK_MESSAGES.bad_response);
  }

  if (response.status === 422) {
    const body = await readJson(response);
    if (isRecord(body) && isStringArray(body.errors)) {
      return { ok: false, errors: body.errors };
    }
    throw new ApiError("bad_response", FALLBACK_MESSAGES.bad_response);
  }

  throw await toStatusError(response);
}

export async function getShoes(): Promise<Shoe[]> {
  const response = await request("/api/shoes", { method: "GET" });

  if (response.status !== 200) {
    throw await toStatusError(response);
  }
  const body = await readJson(response);
  if (!Array.isArray(body) || !body.every(isShoe)) {
    throw new ApiError("bad_response", FALLBACK_MESSAGES.bad_response);
  }
  return body;
}

export async function getQuadrant(): Promise<QuadrantShoe[]> {
  const response = await request("/api/quadrant", { method: "GET" });

  if (response.status !== 200) {
    throw await toStatusError(response);
  }
  const body = await readJson(response);
  if (!Array.isArray(body) || !body.every(isQuadrantShoe)) {
    throw new ApiError("bad_response", FALLBACK_MESSAGES.bad_response);
  }
  return body;
}

export type GetRecommendationsResult =
  | { status: "ok"; ranking: RecommendResponse }
  | { status: "survey_not_found" };

export async function getRecommendations(token: string): Promise<GetRecommendationsResult> {
  const response = await request("/api/recommend", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ survey_token: token }),
  });

  // 422 means the stored token is malformed, so it can never match a survey either.
  if (response.status === 404 || response.status === 422) {
    await response.body?.cancel();
    return { status: "survey_not_found" };
  }
  if (response.status !== 200) {
    throw await toStatusError(response);
  }
  const body = await readJson(response);
  if (!isRecommendResponse(body)) {
    throw new ApiError("bad_response", FALLBACK_MESSAGES.bad_response);
  }
  return { status: "ok", ranking: body };
}

async function request(url: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init);
  } catch (cause) {
    throw new ApiError("unavailable", FALLBACK_MESSAGES.unavailable, { cause });
  }
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch (cause) {
    throw new ApiError("bad_response", FALLBACK_MESSAGES.bad_response, { cause });
  }
}

async function toStatusError(response: Response): Promise<ApiError> {
  const code = toErrorCode(response.status);
  const body: unknown = await response.json().catch(() => null);
  // The proxy always sends a single fixed message, so only errors[0] is surfaced.
  const serverMessage =
    isRecord(body) && isStringArray(body.errors) ? body.errors[0] : undefined;
  return new ApiError(code, serverMessage ?? FALLBACK_MESSAGES[code]);
}

function toErrorCode(status: number): ApiErrorCode {
  if (status === 504) return "timeout";
  if (status === 502 || status === 503) return "unavailable";
  if (status === 400 || status === 413 || status === 415) return "rejected";
  return "bad_response";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isShoe(value: unknown): value is Shoe {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    typeof value.brand === "string" &&
    typeof value.model === "string" &&
    typeof value.version === "string" &&
    GENDERS.includes(value.gender as Gender)
  );
}

function isUnitCoordinate(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= -1 && value <= 1;
}

function isQuadrantShoe(value: unknown): value is QuadrantShoe {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    typeof value.brand === "string" &&
    typeof value.model === "string" &&
    typeof value.version === "string" &&
    GENDERS.includes(value.gender as Gender) &&
    isUnitCoordinate(value.x) &&
    isUnitCoordinate(value.y) &&
    PRIOR_SOURCES.includes(value.prior_source as PriorSource) &&
    typeof value.is_anchor === "boolean" &&
    QUADRANTS.includes(value.quadrant as Quadrant)
  );
}

function isUnitScore(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1;
}

function isNullableUnitScore(value: unknown): value is number | null {
  return value === null || isUnitScore(value);
}

function isCount(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0;
}

function isRecommendation(value: unknown, expectedRank: number): value is Recommendation {
  return (
    isQuadrantShoe(value) &&
    "msrp_usd" in value &&
    (value.msrp_usd === null ||
      (typeof value.msrp_usd === "number" &&
        Number.isFinite(value.msrp_usd) &&
        value.msrp_usd >= 0)) &&
    "price_unknown" in value &&
    value.price_unknown === (value.msrp_usd === null) &&
    "fit_score" in value &&
    isNullableUnitScore(value.fit_score) &&
    "style_score" in value &&
    isNullableUnitScore(value.style_score) &&
    "budget_score" in value &&
    isNullableUnitScore(value.budget_score) &&
    "total_score" in value &&
    isUnitScore(value.total_score) &&
    "confidence" in value &&
    isUnitScore(value.confidence) &&
    "confidence_label" in value &&
    CONFIDENCE_LABELS.includes(value.confidence_label as ConfidenceLabel) &&
    "rank" in value &&
    value.rank === expectedRank &&
    "warnings" in value &&
    isStringArray(value.warnings)
  );
}

function isRecommendResponse(value: unknown): value is RecommendResponse {
  if (!isRecord(value)) return false;
  const { target, terms, gated_out: gatedOut, results } = value;
  return (
    typeof value.scorer_version === "string" &&
    (target === null ||
      (isRecord(target) && isUnitCoordinate(target.x) && isUnitCoordinate(target.y))) &&
    isRecord(terms) &&
    typeof terms.fit === "boolean" &&
    typeof terms.style === "boolean" &&
    typeof terms.budget === "boolean" &&
    isRecord(gatedOut) &&
    isCount(gatedOut.over_budget) &&
    isCount(gatedOut.size_unavailable) &&
    isCount(gatedOut.unplaced) &&
    isStringArray(value.warnings) &&
    Array.isArray(results) &&
    results.every((result, index) => isRecommendation(result, index + 1)) &&
    new Set(results.map((result: Recommendation) => result.id)).size === results.length
  );
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}
