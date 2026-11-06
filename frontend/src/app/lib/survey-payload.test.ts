import { describe, expect, it } from "vitest";

import { toSurveyPayload, type SurveyFormState } from "./survey-payload";
import type { Shoe } from "./types";

const EMPTY_FORM: SurveyFormState = {
  foot_width: "",
  instep: "",
  toe_shape: "",
  arch: "",
  heel_fit: "",
  street_size: "",
  discipline: "",
  terrain: "",
  level: "",
  goal: null,
  budget_cap_usd: "",
  goodAnchors: [],
  badAnchors: [],
};

const SOLUTION: Shoe = {
  id: "shoe-1",
  brand: "La Sportiva",
  model: "Solution",
  version: "",
  gender: "unisex",
};

const MIURA_VS: Shoe = {
  id: "shoe-2",
  brand: "La Sportiva",
  model: "Miura",
  version: "VS",
  gender: "mens",
};

describe("toSurveyPayload", () => {
  it("omits unanswered fields entirely", () => {
    expect(toSurveyPayload(EMPTY_FORM)).toEqual({});
  });

  it("passes answered select values through", () => {
    expect(toSurveyPayload({ ...EMPTY_FORM, foot_width: "wide" }).foot_width).toBe("wide");
  });

  it("converts street_size '9.5' to the number 9.5", () => {
    expect(toSurveyPayload({ ...EMPTY_FORM, street_size: "9.5" }).street_size).toBe(9.5);
  });

  it("converts budget '180' to the number 180", () => {
    expect(toSurveyPayload({ ...EMPTY_FORM, budget_cap_usd: "180" }).budget_cap_usd).toBe(180);
  });

  it("omits a whitespace-only budget", () => {
    expect(toSurveyPayload({ ...EMPTY_FORM, budget_cap_usd: "  " })).not.toHaveProperty(
      "budget_cap_usd",
    );
  });

  it("omits a non-numeric street_size", () => {
    expect(toSurveyPayload({ ...EMPTY_FORM, street_size: "abc" })).not.toHaveProperty(
      "street_size",
    );
  });

  it("omits an Infinity street_size", () => {
    expect(toSurveyPayload({ ...EMPTY_FORM, street_size: "Infinity" })).not.toHaveProperty(
      "street_size",
    );
  });

  it("includes goal when chosen", () => {
    expect(toSurveyPayload({ ...EMPTY_FORM, goal: 0.4 }).goal).toBe(0.4);
  });

  it("includes goal 0 when chosen", () => {
    expect(toSurveyPayload({ ...EMPTY_FORM, goal: 0 }).goal).toBe(0);
  });

  it("omits goal when null", () => {
    expect(toSurveyPayload(EMPTY_FORM)).not.toHaveProperty("goal");
  });

  it("omits anchor lists when empty", () => {
    expect(toSurveyPayload(EMPTY_FORM)).not.toHaveProperty("known_good_shoes");
  });

  it("carries version '' for a base model anchor", () => {
    const payload = toSurveyPayload({
      ...EMPTY_FORM,
      goodAnchors: [{ shoe: SOLUTION, size: "" }],
    });

    expect(payload.known_good_shoes?.[0]).toHaveProperty("version", "");
  });

  it("maps an anchor to brand, model, version and gender only", () => {
    const payload = toSurveyPayload({
      ...EMPTY_FORM,
      badAnchors: [{ shoe: MIURA_VS, size: "" }],
    });

    expect(payload.known_bad_shoes).toEqual([
      { brand: "La Sportiva", model: "Miura", version: "VS", gender: "mens" },
    ]);
  });

  it("never carries id on an anchor", () => {
    const payload = toSurveyPayload({
      ...EMPTY_FORM,
      goodAnchors: [{ shoe: SOLUTION, size: "40" }],
    });

    expect(payload.known_good_shoes?.[0]).not.toHaveProperty("id");
  });

  it("never carries shoe_id on an anchor", () => {
    const payload = toSurveyPayload({
      ...EMPTY_FORM,
      goodAnchors: [{ shoe: SOLUTION, size: "40" }],
    });

    expect(payload.known_good_shoes?.[0]).not.toHaveProperty("shoe_id");
  });

  it("includes anchor size when non-blank", () => {
    const payload = toSurveyPayload({
      ...EMPTY_FORM,
      goodAnchors: [{ shoe: SOLUTION, size: "40.5" }],
    });

    expect(payload.known_good_shoes?.[0].size).toBe("40.5");
  });

  it("omits anchor size when blank", () => {
    const payload = toSurveyPayload({
      ...EMPTY_FORM,
      goodAnchors: [{ shoe: SOLUTION, size: "  " }],
    });

    expect(payload.known_good_shoes?.[0]).not.toHaveProperty("size");
  });

  it("trims anchor size ' 40 ' to '40'", () => {
    const payload = toSurveyPayload({
      ...EMPTY_FORM,
      goodAnchors: [{ shoe: SOLUTION, size: " 40 " }],
    });

    expect(payload.known_good_shoes?.[0].size).toBe("40");
  });
});
