// Browser client. Calls only this app's own route handlers; the browser never
// talks to the FastAPI backend directly.

import type { Shoe, SurveyPayload } from "./types";

export type SubmitResult =
  | { kind: "created" }
  | { kind: "invalid"; errors: string[] }
  | { kind: "failed" };

const GENDERS: readonly unknown[] = ["mens", "womens", "unisex"];

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
