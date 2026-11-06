"use client";

import Link from "next/link";
import { useSyncExternalStore } from "react";

import { SURVEY_TOKEN_KEY } from "../lib/survey-token";

type SavedState = "saved" | "none" | null;

export function SurveySaved() {
  const state = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  // null = unknown (server render / hydration): render nothing to avoid a mismatch.
  if (state === null) return null;

  return (
    <>
      <p className="mt-4">
        {state === "saved"
          ? "Survey saved — your recommendations are coming soon."
          : "No survey yet"}
      </p>
      <Link href="/survey" className="mt-6 inline-block underline">
        {state === "saved" ? "Back to the survey" : "Go to the survey"}
      </Link>
    </>
  );
}

// sessionStorage does not notify same-tab writers; the token only changes before navigation.
function subscribe(): () => void {
  return () => {};
}

function getSnapshot(): SavedState {
  try {
    return sessionStorage.getItem(SURVEY_TOKEN_KEY) !== null ? "saved" : "none";
  } catch {
    return "none";
  }
}

function getServerSnapshot(): SavedState {
  return null;
}
