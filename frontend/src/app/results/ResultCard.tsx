import { useId } from "react";

import {
  CONFIDENCE_COPY,
  formatPrice,
  formatScore,
  toConfidenceReasons,
  toResultWarningText,
  toTermNotUsedReason,
} from "../lib/recommendation-copy";
import type { ScoreTerm } from "../lib/recommendation-copy";
import { toShoeLabel } from "../lib/shoe-label";
import type { Recommendation, RecommendTerms } from "../lib/types";

interface ResultCardProps {
  result: Recommendation;
  terms: RecommendTerms;
}

export function ResultCard({ result, terms }: ResultCardProps) {
  const headingId = useId();
  const isLowConfidence = result.confidence_label === "low";
  const confidence = CONFIDENCE_COPY[result.confidence_label];
  const reasons = toConfidenceReasons(result, terms);
  const termScores: { term: ScoreTerm; label: string; score: number | null }[] = [
    { term: "fit", label: "Fit", score: result.fit_score },
    { term: "style", label: "Style", score: result.style_score },
    { term: "budget", label: "Budget", score: result.budget_score },
  ];

  return (
    <li>
      <article
        aria-labelledby={headingId}
        className={`wrap-anywhere rounded-control border bg-surface p-4 ${
          isLowConfidence ? "border-2 border-dashed border-warning" : "border-border"
        }`}
      >
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <p className="text-sm font-semibold text-muted">Rank {result.rank}</p>
          <h3 id={headingId} className="min-w-0 text-lg font-semibold">
            {toShoeLabel(result)}
          </h3>
        </div>

        <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
          <span
            className={`inline-flex items-center gap-1 rounded-control border px-2 py-0.5 font-medium ${
              isLowConfidence ? "border-warning text-warning" : "border-border"
            }`}
          >
            {isLowConfidence && <WarningIcon />}
            {confidence.title}
          </span>
          <span className="rounded-control border border-border px-2 py-0.5">
            {result.price_unknown || result.msrp_usd === null
              ? "Price unknown"
              : `List price (US) ${formatPrice(result.msrp_usd)}`}
          </span>
        </div>

        {isLowConfidence ? (
          <p className="mt-2 text-sm text-warning">
            Treat this as a rough starting point: {reasons.length > 0 ? `${reasons.join("; ")}.` : confidence.explanation}
          </p>
        ) : (
          <p className="mt-2 text-sm text-muted">{confidence.explanation}</p>
        )}

        <dl className="mt-3 grid gap-1 text-sm">
          <ScoreRow label="Match" value={`${formatScore(result.total_score)}/100`} />
          {termScores.map(({ term, label, score }) =>
            score === null ? (
              <ScoreRow
                key={term}
                label={label}
                value="Not used"
                note={toTermNotUsedReason(term)}
              />
            ) : (
              <ScoreRow key={term} label={label} value={`${formatScore(score)}/100`}
                note={
                  term === "budget" && result.price_unknown
                    ? "price unknown, so this is a neutral estimate"
                    : undefined
                }
              />
            ),
          )}
        </dl>

        {result.warnings.length > 0 && (
          <ul className="mt-3 list-disc pl-5 text-sm text-muted">
            {result.warnings.map((code) => (
              <li key={code} data-code={code}>{toResultWarningText(code)}</li>
            ))}
          </ul>
        )}
      </article>
    </li>
  );
}

function ScoreRow({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="flex flex-wrap gap-x-2">
      <dt className="font-medium">{label}</dt>
      <dd className="min-w-0">
        <span>{value}</span>
        {note !== undefined && <span className="text-muted"> ({note})</span>}
      </dd>
    </div>
  );
}

function WarningIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" width="14" height="14" fill="currentColor">
      <path d="M10 2 1 18h18L10 2Zm-1 6h2v5H9V8Zm0 6h2v2H9v-2Z" />
    </svg>
  );
}
