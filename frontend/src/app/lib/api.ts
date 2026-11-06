import {
  GENDERS,
  PRIOR_SOURCES,
  QUADRANTS,
  type Gender,
  type PriorSource,
  type Quadrant,
  type QuadrantShoe,
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

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}
