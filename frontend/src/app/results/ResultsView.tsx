"use client";

import Link from "next/link";
import { useEffect, useId, useRef, useState, useSyncExternalStore } from "react";

import { QuadrantChart } from "../components/QuadrantChart";
import { SURVEY_TOKEN_KEY, fetchRecommendations } from "../lib/api";
import {
  CONFIDENCE_COPY,
  toGatedOutSentences,
  toPriceUnknownSentence,
  toSurveyWarningText,
} from "../lib/recommendation-copy";
import type { ConfidenceLabel, RecommendResponse } from "../lib/types";

import { ResultCard } from "./ResultCard";

type ViewState =
  | { status: "loading" }
  | { status: "ready"; ranking: RecommendResponse }
  | { status: "not-found" }
  | { status: "failed" };

const HIGHLIGHT_COUNT = 3;
const CONFIDENCE_LEVELS: readonly ConfidenceLabel[] = ["high", "medium", "low"];
const FAILED_MESSAGE = "We couldn't load your results. Please try again.";

export function ResultsView() {
  const token = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const [state, setState] = useState<ViewState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [previousToken, setPreviousToken] = useState(token);
  const statusRef = useRef<HTMLParagraphElement>(null);
  const alertRef = useRef<HTMLDivElement>(null);

  // Adjusted during render (not in the effect) so a new token never shows the previous token's result.
  // An emptied token is skipped: a 404 clears it and must keep the not-found view.
  if (token !== previousToken) {
    setPreviousToken(token);
    if (token) setState({ status: "loading" });
  }

  useEffect(() => {
    if (!token) return;
    let isCurrent = true;
    const controller = new AbortController();
    fetchRecommendations(token, controller.signal).then(
      (result) => {
        if (!isCurrent) return;
        if (result.kind === "ranked") {
          setState({ status: "ready", ranking: result.ranking });
          return;
        }
        try {
          sessionStorage.removeItem(SURVEY_TOKEN_KEY);
        } catch {
          // Storage can be blocked; the not-found message still shows, and a stale token only costs one more 404.
        }
        setState({ status: "not-found" });
      },
      () => {
        // Covers an abort too, which only happens after unmount or a token change (isCurrent false).
        if (isCurrent) setState({ status: "failed" });
      },
    );
    return () => {
      isCurrent = false;
      controller.abort();
    };
  }, [token, attempt]);

  useEffect(() => {
    if (state.status === "not-found") statusRef.current?.focus();
    if (state.status === "failed") alertRef.current?.focus();
  }, [state.status]);

  function handleRetry() {
    // The button unmounts on click, so hand focus to the always-mounted status region.
    statusRef.current?.focus();
    setState({ status: "loading" });
    setAttempt((previous) => previous + 1);
  }

  // Fetch state wins over the snapshot: clearing the token on a 404 must not read as "no survey".
  const hasNoSurvey = token === "" && state.status === "loading";

  return (
    <div className="mt-4 flex flex-col gap-8">
      {/* Mounted throughout so assistive tech keeps observing the live region. */}
      <p ref={statusRef} tabIndex={-1} role="status" className="text-muted">
        {token !== null && !hasNoSurvey && state.status === "loading" && "Loading your results…"}
        {state.status === "ready" && toRankedCount(state.ranking.results.length)}
        {state.status === "not-found" && "We couldn't find your survey."}
      </p>
      {hasNoSurvey && (
        <div className="flex flex-col items-start gap-3">
          <p>You haven&apos;t taken the survey yet.</p>
          <SurveyLink>Take the survey</SurveyLink>
        </div>
      )}
      {state.status === "not-found" && <SurveyLink>Take the survey again</SurveyLink>}
      {state.status === "failed" && (
        <div ref={alertRef} tabIndex={-1} role="alert" className="flex flex-col items-start gap-3 rounded-control border border-danger p-3 text-danger">
          <p>{FAILED_MESSAGE}</p>
          <button
            type="button"
            onClick={handleRetry}
            className="min-h-11 rounded-control bg-accent px-6 font-medium text-accent-foreground"
          >
            Try again
          </button>
        </div>
      )}
      {state.status === "ready" && <ReadyResults ranking={state.ranking} />}
    </div>
  );
}

function ReadyResults({ ranking }: { ranking: RecommendResponse }) {
  const aboutHeadingId = useId();
  const rankedHeadingId = useId();
  const chartHeadingId = useId();
  const { results } = ranking;
  const gatedOutSentences = toGatedOutSentences(ranking.gated_out);

  if (results.length === 0) {
    return (
      <div className="flex flex-col gap-3">
        <p>No shoes matched your survey.</p>
        <SurveyLink>Adjust your survey</SurveyLink>
        {gatedOutSentences.length > 0 && (
          <ul className="list-disc pl-5 text-sm text-muted">
            {gatedOutSentences.map((sentence) => (
              <li key={sentence}>{sentence}</li>
            ))}
          </ul>
        )}
      </div>
    );
  }

  const priceUnknownCount = results.filter((result) => result.price_unknown).length;
  const notes = [
    ...ranking.warnings.map(toSurveyWarningText),
    ...gatedOutSentences,
    ...(priceUnknownCount > 0 ? [toPriceUnknownSentence(priceUnknownCount)] : []),
  ];

  return (
    <>
      <section aria-labelledby={aboutHeadingId} className="flex flex-col gap-3">
        <h2 id={aboutHeadingId} className="text-xl font-semibold">About these results</h2>
        {notes.length > 0 && (
          <ul className="list-disc pl-5 text-sm">
            {notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        )}
        <p className="text-sm text-muted">Each shoe has a confidence label:</p>
        <ul className="list-disc pl-5 text-sm text-muted">
          {CONFIDENCE_LEVELS.map((level) => (
            <li key={level}>
              <span className="font-medium">{CONFIDENCE_COPY[level].title}:</span> {CONFIDENCE_COPY[level].explanation}
            </li>
          ))}
        </ul>
      </section>
      <section aria-labelledby={rankedHeadingId} className="flex flex-col gap-3">
        <h2 id={rankedHeadingId} className="text-xl font-semibold">Ranked shoes</h2>
        {/* role="list" because list-none drops list semantics in Safari. */}
        <ol role="list" className="flex list-none flex-col gap-3 p-0">
          {results.map((result) => (
            <ResultCard key={result.id} result={result} terms={ranking.terms} />
          ))}
        </ol>
      </section>
      <section aria-labelledby={chartHeadingId} className="flex flex-col gap-3">
        <h2 id={chartHeadingId} className="text-xl font-semibold">Where they sit on the quadrant</h2>
        <p className="text-sm text-muted">Your top 3 are highlighted. Only ranked shoes appear; shoes that were left out are not shown.</p>
        {/* Narrow cap: only a few labelled shoes, so the chart stays near body-small text on wide screens. */}
        <div className="mx-auto w-full max-w-sm">
          <QuadrantChart
            shoes={results}
            target={ranking.target ?? undefined}
            highlightIds={results.slice(0, HIGHLIGHT_COUNT).map((result) => result.id)}
          />
        </div>
      </section>
    </>
  );
}

function SurveyLink({ children }: { children: string }) {
  return (
    <Link href="/survey" className="inline-flex min-h-11 items-center underline">
      {children}
    </Link>
  );
}

function toRankedCount(count: number): string {
  return `${count} ${count === 1 ? "shoe" : "shoes"} ranked.`;
}

// sessionStorage does not notify same-tab writers; the token only changes before navigation.
function subscribe(): () => void {
  return () => {};
}

// "" = no token; null (server render / hydration) = unknown, so nothing flashes before hydration.
function getSnapshot(): string | null {
  try {
    return sessionStorage.getItem(SURVEY_TOKEN_KEY) ?? "";
  } catch {
    return "";
  }
}

function getServerSnapshot(): string | null {
  return null;
}
