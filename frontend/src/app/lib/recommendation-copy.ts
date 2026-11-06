import type { ConfidenceLabel, GatedOut, Recommendation, RecommendTerms } from "./types";

export type ScoreTerm = "fit" | "style" | "budget";

export const CONFIDENCE_COPY: Record<ConfidenceLabel, { title: string; explanation: string }> = {
  high: {
    title: "High confidence",
    explanation: "This match rests on the answers you gave and our placement of the shoe. It is still an estimate.",
  },
  medium: {
    title: "Medium confidence",
    explanation: "Some of the information behind this match is thin or estimated, so the ranking could shift.",
  },
  low: {
    title: "Low confidence",
    explanation: "Much of the information behind this match is missing or estimated.",
  },
};

const CATALOG_FIELD_WORDS: Record<string, string> = {
  last_shape: "last shape",
  downturn: "downturn",
  closure: "closure type",
};

const CATALOG_FIELD_PREFIX = "catalog_field_missing:";
const ANCHOR_PREFIX = "anchor_not_in_catalog:";

export function toResultWarningText(code: string): string {
  if (code === "reported_good_fit") return "You said this shoe fits you well.";
  if (code === "reported_poor_fit") {
    return "You said this shoe fit poorly. It is still ranked, not hidden.";
  }
  if (code.startsWith(CATALOG_FIELD_PREFIX)) {
    return `We don't have this shoe's ${toFieldWords(code)}, so that part of the fit score is neutral.`;
  }
  return "There is a note about this result that we can't describe yet.";
}

export function toSurveyWarningText(code: string): string {
  if (code === "no_target") {
    return "You didn't choose a discipline, so there's no style target.";
  }
  if (code === "target_recomputed_without_goal") {
    // The questionnaire does not ask the comfort-vs-performance goal yet, so every target is derived.
    return "Your style target comes from your discipline, terrain and level.";
  }
  if (code === "no_scoring_inputs") {
    return "You didn't give us anything to score on, so every shoe scores the same.";
  }
  if (code.startsWith(ANCHOR_PREFIX)) {
    const count = Number(code.slice(ANCHOR_PREFIX.length));
    if (Number.isInteger(count) && count > 0) {
      return count === 1
        ? "1 shoe you listed isn't in our catalogue, so it was ignored."
        : `${count} shoes you listed aren't in our catalogue, so they were ignored.`;
    }
  }
  if (code.startsWith(CATALOG_FIELD_PREFIX)) {
    return `We don't have the ${toFieldWords(code)} for a shoe you listed, so it tells us less about your fit.`;
  }
  return "There is a note about your survey that we can't describe yet.";
}

export function toTermNotUsedReason(term: ScoreTerm): string {
  switch (term) {
    case "fit":
      // Mirrors score.py: only foot width, toe shape, instep and catalogue-matched anchors feed Fit.
      return "you didn't give your foot width, toe shape or instep, or name a shoe we know";
    case "style":
      return "no discipline was chosen, so there's no style target";
    case "budget":
      return "no budget was given";
  }
}

export function toGatedOutSentences(gatedOut: GatedOut): string[] {
  const sentences: string[] = [];
  const { over_budget: overBudget, size_unavailable: noSize, unplaced } = gatedOut;
  if (overBudget > 0) {
    sentences.push(
      `${overBudget} ${plural(overBudget, "shoe", "shoes")} priced over your budget ${plural(overBudget, "was", "were")} left out.`,
    );
  }
  if (noSize > 0) {
    sentences.push(
      `${noSize} ${plural(noSize, "shoe", "shoes")} not available in your size ${plural(noSize, "was", "were")} left out.`,
    );
  }
  if (unplaced > 0) {
    sentences.push(
      `${unplaced} ${plural(unplaced, "shoe", "shoes")} we couldn't place on the map ${plural(unplaced, "was", "were")} left out.`,
    );
  }
  return sentences;
}

export function toPriceUnknownSentence(count: number): string {
  return count === 1
    ? "1 shoe has no known price. It's included, but we can't confirm it's within your budget."
    : `${count} shoes have no known price. They're included, but we can't confirm they're within your budget.`;
}

export function toConfidenceReasons(
  result: Pick<Recommendation, "prior_source">,
  terms: RecommendTerms,
): string[] {
  const reasons: string[] = [];
  // With no style target the placement term is dropped, so a spec placement cannot lower confidence.
  if (result.prior_source === "spec" && terms.style) {
    reasons.push("this shoe's position is estimated from its specs");
  }
  if (!terms.style) reasons.push("there's no style target");
  if (!terms.fit) reasons.push("there's no fit information");
  return reasons;
}

export function formatScore(score: number): string {
  return String(Math.round(score * 100));
}

const USD_WHOLE = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});
const USD_CENTS = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

export function formatPrice(usd: number): string {
  return (Number.isInteger(usd) ? USD_WHOLE : USD_CENTS).format(usd);
}

function toFieldWords(code: string): string {
  return CATALOG_FIELD_WORDS[code.slice(CATALOG_FIELD_PREFIX.length)] ?? "some catalogue details";
}

function plural(count: number, one: string, many: string): string {
  return count === 1 ? one : many;
}
