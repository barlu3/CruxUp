import { describe, expect, it } from "vitest";

import shoes from "../../../e2e/fixtures/shoes.json";
import { interpretErrors } from "./errors";
import type { SelectedAnchor } from "./payload";
import type { Shoe } from "./types";

const all = shoes as Shoe[];
const pick = (model: string, version: string): SelectedAnchor => ({
  shoe: all.find((s) => s.model === model && s.version === version)!,
  size: "",
});
const good = [pick("Instinct", "VSR")];
const bad = [pick("Drago", ""), pick("Solution", ""), pick("Origin", "")];

const charset = (where: string) =>
  `${where}: 'size' contains [','] -- it records a brand size, not free text (D4: no direct identifiers)`;

describe("interpretErrors", () => {
  it("translates the charset shape and names the shoe", () => {
    const r = interpretErrors([charset("known_good_shoes[0]")], good, bad);
    expect(r.unmatched).toEqual([]);
    expect(r.sizeProblems).toEqual([
      {
        shoeId: good[0].shoe.id,
        message:
          "Size for Scarpa Instinct VSR (unisex): use only letters, numbers, spaces and . / + - (for example 41 or 8.5).",
      },
    ]);
    expect(r.sizeProblems[0].message).not.toMatch(/known_|D4/);
  });

  it("maps the index to the i-th shoe of the right list", () => {
    const r = interpretErrors([charset("known_bad_shoes[2]")], good, bad);
    expect(r.sizeProblems[0].shoeId).toBe(bad[2].shoe.id);
    expect(r.sizeProblems[0].message).toContain("Scarpa Origin (unisex)");
  });

  it("translates the length shape", () => {
    const r = interpretErrors(["known_bad_shoes[1]: 'size' is 70 characters, maximum 64"], good, bad);
    expect(r.sizeProblems).toEqual([
      {
        shoeId: bad[1].shoe.id,
        message: "Size for La Sportiva Solution (unisex): use 64 characters or fewer.",
      },
    ]);
  });

  it("keeps unknown messages, and out-of-range indexes, as unmatched raw text", () => {
    const odd = "known_good_shoes[0]: shoe is ambiguous";
    const gone = charset("known_good_shoes[5]");
    const r = interpretErrors([odd, gone, "<b>x</b>"], good, bad);
    expect(r.sizeProblems).toEqual([]);
    expect(r.unmatched).toEqual([odd, gone, "<b>x</b>"]);
  });

  it("handles a mix", () => {
    const r = interpretErrors(["nope", charset("known_good_shoes[0]")], good, bad);
    expect(r.sizeProblems).toHaveLength(1);
    expect(r.unmatched).toEqual(["nope"]);
  });
});
