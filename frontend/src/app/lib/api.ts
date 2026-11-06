// Browser client. Calls only this app's own route handlers; the browser never
// talks to the FastAPI backend directly.

import type { QuadrantShoe, Shoe, SurveyPayload } from "./types";

export type SubmitResult =
  | { kind: "created" }
  | { kind: "invalid"; errors: string[] }
  | { kind: "failed" };

const GENDERS: readonly unknown[] = ["mens", "womens", "unisex"];
const PRIOR_SOURCES: readonly unknown[] = ["corpus", "hand", "spec"];
const QUADRANTS: readonly unknown[] = ["Q1", "Q2", "Q3", "Q4"];

function isShoe(v: unknown): v is Shoe {
  if (typeof v !== "object" || v === null) return false;
  const r = v as Record<string, unknown>;
  return (
    typeof r.id === "string" &&
    typeof r.brand === "string" &&
    typeof r.model === "string" &&
    typeof r.version === "string" &&
    GENDERS.includes(r.gender)
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
    PRIOR_SOURCES.includes(r.prior_source) &&
    typeof r.is_anchor === "boolean" &&
    QUADRANTS.includes(r.quadrant)
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
    if (res.status === 201) return { kind: "created" };
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
