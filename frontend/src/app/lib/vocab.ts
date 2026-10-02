// Option lists, labels and numeric bounds. Mirrors backend/app/survey/schema.py
// (ENUMS, PY_ONLY_ENUMS and the numeric constants); vocab.test.ts fails if
// either side drifts.

import type { Gender } from "./types";

export const ENUM_FIELDS = [
  "foot_width",
  "instep",
  "toe_shape",
  "arch",
  "heel_fit",
  "discipline",
  "terrain",
  "level",
] as const;

export type EnumField = (typeof ENUM_FIELDS)[number];

export const ENUM_VOCAB: Record<EnumField, readonly string[]> = {
  foot_width: ["narrow", "medium", "wide"],
  instep: ["low", "medium", "high"],
  toe_shape: ["egyptian", "greek", "roman"],
  arch: ["low", "medium", "high"],
  heel_fit: ["narrow", "medium", "wide"],
  discipline: ["boulder", "sport", "trad", "gym"],
  terrain: ["slab", "vertical", "overhang", "crack"],
  level: ["beginner", "intermediate", "advanced", "elite"],
};

export const OPTION_LABELS: Record<EnumField, Record<string, string>> = {
  foot_width: { narrow: "Narrow", medium: "Medium", wide: "Wide" },
  instep: { low: "Low", medium: "Medium", high: "High" },
  toe_shape: {
    egyptian: "Egyptian — big toe longest",
    greek: "Greek — second toe longest",
    roman: "Roman — first toes about even",
  },
  arch: { low: "Low", medium: "Medium", high: "High" },
  heel_fit: { narrow: "Narrow", medium: "Medium", wide: "Wide" },
  discipline: { boulder: "Bouldering", sport: "Sport", trad: "Trad", gym: "Gym" },
  terrain: { slab: "Slab", vertical: "Vertical", overhang: "Overhang", crack: "Crack" },
  level: {
    beginner: "Beginner",
    intermediate: "Intermediate",
    advanced: "Advanced",
    elite: "Elite",
  },
};

/** street_size: 0 < v <= 20, at most 1 decimal. */
export const STREET_SIZE_BOUNDS = { minExclusive: 0, max: 20, decimals: 1 } as const;

/** budget_cap_usd: 0 < v < 100000, at most 2 decimals. */
export const BUDGET_BOUNDS = {
  minExclusive: 0,
  limitExclusive: 100_000,
  decimals: 2,
} as const;

/** `<input type="number">` attributes, derived from the drift-tested bounds. */
const decimalStep = (decimals: number) => 10 ** -decimals;
export const STREET_SIZE_INPUT = {
  min: decimalStep(STREET_SIZE_BOUNDS.decimals),
  max: STREET_SIZE_BOUNDS.max,
  step: decimalStep(STREET_SIZE_BOUNDS.decimals),
} as const;
export const BUDGET_INPUT = {
  min: decimalStep(BUDGET_BOUNDS.decimals),
  max: Number((BUDGET_BOUNDS.limitExclusive - decimalStep(BUDGET_BOUNDS.decimals)).toFixed(BUDGET_BOUNDS.decimals)),
  step: decimalStep(BUDGET_BOUNDS.decimals),
} as const;

export const GENDER_LABELS: Record<Gender, string> = {
  mens: "men's",
  womens: "women's",
  unisex: "unisex",
};

/** anchors.py ANCHOR_SIZE_MAX_LEN (drift-tested). */
export const ANCHOR_SIZE_MAX_LENGTH = 64;

/**
 * The non-alphanumeric characters anchors.py SIZE_ALLOWED_CHARS accepts in a
 * size, besides digits and ASCII letters (drift-tested).
 */
export const SIZE_ALLOWED_EXTRA = " ./+-\u00bd\u2153\u2154\u00bc\u00be";

export const SIZE_HINT =
  "As printed on the shoe, e.g. 41 or 8.5. Use letters, numbers, spaces and . / + - only (fractions such as ½ ¼ ¾ are fine).";

const DECIMAL_WORDS = ["no", "one", "two", "three"];
const places = (n: number) =>
  `at most ${DECIMAL_WORDS[n] ?? n} decimal place${n === 1 ? "" : "s"}`;

export const STREET_SIZE_HINT = `Your usual US street shoe size, for example 9.5. Between ${STREET_SIZE_INPUT.min} and ${STREET_SIZE_INPUT.max}, ${places(STREET_SIZE_BOUNDS.decimals)}.`;

export const BUDGET_HINT = `The most you want to spend, in US dollars. More than ${BUDGET_BOUNDS.minExclusive} and under ${BUDGET_BOUNDS.limitExclusive.toLocaleString("en-US")}, ${places(BUDGET_BOUNDS.decimals)}.`;
