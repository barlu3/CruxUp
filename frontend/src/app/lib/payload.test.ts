import { describe, expect, it } from "vitest";

import shoes from "../../../e2e/fixtures/shoes.json";
import { buildPayload, emptyFormState, type FormState } from "./payload";
import type { Shoe } from "./types";

const all = shoes as Shoe[];
const find = (model: string, version: string): Shoe => {
  const s = all.find((x) => x.model === model && x.version === version);
  if (!s) throw new Error(`fixture lacks ${model} ${version}`);
  return s;
};

describe("buildPayload", () => {
  it("returns {} when nothing is set", () => {
    expect(buildPayload(emptyFormState())).toEqual({});
  });

  it("sends an anchors-only answer with no fit keys and no nulls", () => {
    const state: FormState = {
      ...emptyFormState(),
      known_good_shoes: [{ shoe: find("Instinct", "VSR"), size: "" }],
    };
    const payload = buildPayload(state);
    expect(payload).toEqual({
      known_good_shoes: [
        { brand: "Scarpa", model: "Instinct", version: "VSR", gender: "unisex" },
      ],
    });
    expect(Object.keys(payload)).toEqual(["known_good_shoes"]);
    expect(JSON.stringify(payload)).not.toContain("null");
  });

  it("preserves version '' for the base Solution and never sends id", () => {
    const state: FormState = {
      ...emptyFormState(),
      known_bad_shoes: [{ shoe: find("Solution", ""), size: "" }],
    };
    const entry = buildPayload(state).known_bad_shoes?.[0];
    expect(entry).toEqual({
      brand: "La Sportiva",
      model: "Solution",
      version: "",
      gender: "unisex",
    });
    expect(entry).not.toHaveProperty("id");
  });

  it("sends size only when non-empty", () => {
    const state: FormState = {
      ...emptyFormState(),
      known_good_shoes: [
        { shoe: find("Instinct", "VS"), size: "  " },
        { shoe: find("Instinct", "VSR"), size: "EU 41.5" },
      ],
    };
    const [a, b] = buildPayload(state).known_good_shoes ?? [];
    expect(a).not.toHaveProperty("size");
    expect(b).toHaveProperty("size", "EU 41.5");
  });

  it("sends selects as strings and numbers as numbers, omitting blanks", () => {
    const payload = buildPayload({
      ...emptyFormState(),
      foot_width: "wide",
      toe_shape: "greek",
      street_size: "9.5",
      budget_cap_usd: "150.25",
      level: "elite",
    });
    expect(payload).toEqual({
      foot_width: "wide",
      toe_shape: "greek",
      street_size: 9.5,
      budget_cap_usd: 150.25,
      level: "elite",
    });
  });

  it("omits numbers that are not finite and never sends goal keys", () => {
    const payload = buildPayload({
      ...emptyFormState(),
      street_size: "abc",
      budget_cap_usd: "  ",
    });
    expect(payload).toEqual({});
  });

  it("omits empty anchor lists", () => {
    expect(buildPayload({ ...emptyFormState(), arch: "high" })).toEqual({
      arch: "high",
    });
  });

  it("preserves the order of each list (error indexes map back to chosen shoes)", () => {
    const [a, b, c] = [find("Instinct", "VS"), find("Instinct", "VSR"), find("Solution", "")];
    const payload = buildPayload({
      ...emptyFormState(),
      known_good_shoes: [
        { shoe: c, size: "" },
        { shoe: a, size: "" },
        { shoe: b, size: "" },
      ],
    });
    expect(payload.known_good_shoes?.map((e) => `${e.model}/${e.version}`)).toEqual([
      "Solution/",
      "Instinct/VS",
      "Instinct/VSR",
    ]);
  });
});
