import { describe, expect, it } from "vitest";

import {
  CONFIDENCE_COPY,
  formatPrice,
  formatScore,
  toConfidenceReasons,
  toGatedOutSentences,
  toPriceUnknownSentence,
  toResultWarningText,
  toSurveyWarningText,
  toTermNotUsedReason,
} from "./recommendation-copy";

const ALL_TERMS = { fit: true, style: true, budget: true };

describe("toResultWarningText", () => {
  it("explains a reported good fit", () => {
    expect(toResultWarningText("reported_good_fit")).toBe("You said this shoe fits you well.");
  });

  it("says a reported poor fit is still ranked", () => {
    expect(toResultWarningText("reported_poor_fit")).toMatch(/still ranked/);
  });

  it("names a missing last shape", () => {
    expect(toResultWarningText("catalog_field_missing:last_shape")).toBe(
      "We don't have this shoe's last shape, so that part of the fit score is neutral.",
    );
  });

  it("names a missing downturn", () => {
    expect(toResultWarningText("catalog_field_missing:downturn")).toContain("downturn");
  });

  it("names a missing closure type", () => {
    expect(toResultWarningText("catalog_field_missing:closure")).toContain("closure type");
  });

  it("uses vague wording for an unknown missing field", () => {
    expect(toResultWarningText("catalog_field_missing:weight")).toContain("some catalogue details");
  });

  it("falls back to a generic sentence for an unknown code", () => {
    expect(toResultWarningText("brand_new_code")).toBe("There is a note about this result that we can't describe yet.");
  });
});

describe("toSurveyWarningText", () => {
  it("explains a missing target", () => {
    expect(toSurveyWarningText("no_target")).toMatch(/no style target/i);
  });

  it("explains a target recomputed without a goal", () => {
    expect(toSurveyWarningText("target_recomputed_without_goal")).toBe(
      "Your style target comes from your discipline, terrain and level, because you didn't set the style slider.",
    );
  });

  it("uses the singular for one missing anchor shoe", () => {
    expect(toSurveyWarningText("anchor_not_in_catalog:1")).toBe(
      "1 shoe you listed isn't in our catalogue, so it was ignored.",
    );
  });

  it("uses the plural for several missing anchor shoes", () => {
    expect(toSurveyWarningText("anchor_not_in_catalog:3")).toBe(
      "3 shoes you listed aren't in our catalogue, so they were ignored.",
    );
  });

  it("says every shoe scores the same without scoring inputs", () => {
    expect(toSurveyWarningText("no_scoring_inputs")).toContain("every shoe scores the same");
  });

  it("names the missing field on a listed shoe", () => {
    expect(toSurveyWarningText("catalog_field_missing:closure")).toContain("closure type");
  });

  it("says a listed shoe's missing field tells us less about your fit", () => {
    expect(toSurveyWarningText("catalog_field_missing:closure")).toContain("so it tells us less about your fit.");
  });

  it("falls back to a generic sentence for an unknown code", () => {
    expect(toSurveyWarningText("brand_new_code")).toBe("There is a note about your survey that we can't describe yet.");
  });

  it("falls back for an anchor code with a malformed count", () => {
    expect(toSurveyWarningText("anchor_not_in_catalog:abc")).toBe("There is a note about your survey that we can't describe yet.");
  });
});

describe("toTermNotUsedReason", () => {
  it("explains an unused fit term", () => {
    expect(toTermNotUsedReason("fit")).toBe("you didn't answer the fit questions or list shoes");
  });

  it("explains an unused style term", () => {
    expect(toTermNotUsedReason("style")).toBe("no discipline was chosen, so there's no style target");
  });

  it("explains an unused budget term", () => {
    expect(toTermNotUsedReason("budget")).toBe("no budget was given");
  });
});

describe("toGatedOutSentences", () => {
  it("describes one shoe over budget in the singular", () => {
    expect(toGatedOutSentences({ over_budget: 1, size_unavailable: 0, unplaced: 0 })).toEqual([
      "1 shoe priced over your budget was left out.",
    ]);
  });

  it("describes several shoes over budget in the plural", () => {
    expect(toGatedOutSentences({ over_budget: 4, size_unavailable: 0, unplaced: 0 })).toEqual([
      "4 shoes priced over your budget were left out.",
    ]);
  });

  it("describes one shoe without your size in the singular", () => {
    expect(toGatedOutSentences({ over_budget: 0, size_unavailable: 1, unplaced: 0 })).toEqual([
      "1 shoe not available in your size was left out.",
    ]);
  });

  it("describes several shoes without your size in the plural", () => {
    expect(toGatedOutSentences({ over_budget: 0, size_unavailable: 2, unplaced: 0 })).toEqual([
      "2 shoes not available in your size were left out.",
    ]);
  });

  it("describes one unplaced shoe in the singular", () => {
    expect(toGatedOutSentences({ over_budget: 0, size_unavailable: 0, unplaced: 1 })).toEqual([
      "1 shoe we couldn't place on the map was left out.",
    ]);
  });

  it("describes several unplaced shoes in the plural", () => {
    expect(toGatedOutSentences({ over_budget: 0, size_unavailable: 0, unplaced: 5 })).toEqual([
      "5 shoes we couldn't place on the map were left out.",
    ]);
  });

  it("returns one sentence per non-zero count in a fixed order", () => {
    expect(toGatedOutSentences({ over_budget: 2, size_unavailable: 0, unplaced: 1 })).toHaveLength(2);
  });

  it("returns nothing when all counts are zero", () => {
    expect(toGatedOutSentences({ over_budget: 0, size_unavailable: 0, unplaced: 0 })).toEqual([]);
  });
});

describe("toPriceUnknownSentence", () => {
  it("uses the singular for one shoe", () => {
    expect(toPriceUnknownSentence(1)).toBe(
      "1 shoe has no known price. It's included, but we can't confirm it's within your budget.",
    );
  });

  it("uses the plural for several shoes", () => {
    expect(toPriceUnknownSentence(3)).toBe(
      "3 shoes have no known price. They're included, but we can't confirm they're within your budget.",
    );
  });
});

describe("CONFIDENCE_COPY", () => {
  it("titles high confidence", () => {
    expect(CONFIDENCE_COPY.high.title).toBe("High confidence");
  });

  it("titles medium confidence", () => {
    expect(CONFIDENCE_COPY.medium.title).toBe("Medium confidence");
  });

  it("titles low confidence", () => {
    expect(CONFIDENCE_COPY.low.title).toBe("Low confidence");
  });

  it("does not overclaim for high confidence", () => {
    expect(CONFIDENCE_COPY.high.explanation).toBe(
      "This match rests on the answers you gave and our placement of the shoe. It is still an estimate.",
    );
  });

  it("says medium confidence could shift the ranking", () => {
    expect(CONFIDENCE_COPY.medium.explanation).toBe(
      "Some of the information behind this match is thin or estimated, so the ranking could shift.",
    );
  });

  it("ends the low confidence explanation with a period", () => {
    expect(CONFIDENCE_COPY.low.explanation).toMatch(/\.$/);
  });
});

describe("toConfidenceReasons", () => {
  it("blames spec-estimated positions", () => {
    expect(toConfidenceReasons({ prior_source: "spec" }, ALL_TERMS)).toEqual([
      "this shoe's position is estimated from its specs",
    ]);
  });

  it("omits the spec reason when there is no style target", () => {
    expect(toConfidenceReasons({ prior_source: "spec" }, { ...ALL_TERMS, style: false })).toEqual([
      "there's no style target",
    ]);
  });

  it("blames a missing style target", () => {
    expect(toConfidenceReasons({ prior_source: "corpus" }, { ...ALL_TERMS, style: false })).toEqual([
      "there's no style target",
    ]);
  });

  it("blames missing fit information", () => {
    expect(toConfidenceReasons({ prior_source: "hand" }, { ...ALL_TERMS, fit: false })).toEqual([
      "there's no fit information",
    ]);
  });

  it("lists every applicable reason", () => {
    expect(toConfidenceReasons({ prior_source: "spec" }, { fit: false, style: true, budget: true })).toHaveLength(2);
  });

  it("returns nothing when the data is solid", () => {
    expect(toConfidenceReasons({ prior_source: "corpus" }, ALL_TERMS)).toEqual([]);
  });
});

describe("formatScore", () => {
  it("rounds to an integer out of 100", () => {
    expect(formatScore(0.82)).toBe("82");
  });

  it("rounds halves up", () => {
    expect(formatScore(0.745)).toBe("75");
  });

  it("renders zero", () => {
    expect(formatScore(0)).toBe("0");
  });

  it("renders one as 100", () => {
    expect(formatScore(1)).toBe("100");
  });
});

describe("formatPrice", () => {
  it("drops the cents on a whole price", () => {
    expect(formatPrice(189)).toBe("$189");
  });

  it("keeps the cents on a fractional price", () => {
    expect(formatPrice(189.5)).toBe("$189.50");
  });
});
