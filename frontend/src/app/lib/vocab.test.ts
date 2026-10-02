import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import {
  BUDGET_BOUNDS,
  ANCHOR_SIZE_MAX_LENGTH,
  BUDGET_HINT,
  BUDGET_INPUT,
  SIZE_ALLOWED_EXTRA,
  STREET_SIZE_HINT,
  STREET_SIZE_INPUT,
  ENUM_FIELDS,
  ENUM_VOCAB,
  OPTION_LABELS,
  STREET_SIZE_BOUNDS,
} from "./vocab";

// Plain path arithmetic: vite rewrites `new URL("<literal>", import.meta.url)`.
const schemaPath = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../../../../backend/app/survey/schema.py",
);
const source = readFileSync(schemaPath, "utf8");

function parseDict(name: string): Record<string, string[]> {
  const start = source.indexOf(`${name}: dict[str, set[str]] = {`);
  if (start < 0) throw new Error(`schema.py: ${name} not found`);
  const end = source.indexOf("\n}", start);
  const body = source.slice(start, end);
  const out: Record<string, string[]> = {};
  for (const m of body.matchAll(/"(\w+)":\s*\{([^}]*)\}/g)) {
    out[m[1]] = [...m[2].matchAll(/"(\w+)"/g)].map((v) => v[1]);
  }
  if (Object.keys(out).length === 0) throw new Error(`parsed nothing from ${name}`);
  return out;
}

function parseConst(name: string): number {
  const m = source.match(new RegExp(`^${name}\\s*=\\s*([0-9_.]+)`, "m"));
  if (!m) throw new Error(`schema.py: constant ${name} not found`);
  return Number(m[1].replace(/_/g, ""));
}

function parsePair(a: string, b: string): [number, number] {
  const m = source.match(new RegExp(`^${a},\\s*${b}\\s*=\\s*([0-9_.]+),\\s*([0-9_.]+)`, "m"));
  if (!m) throw new Error(`schema.py: pair ${a}, ${b} not found`);
  return [Number(m[1]), Number(m[2])];
}

describe("vocabulary drift against backend/app/survey/schema.py", () => {
  const py = { ...parseDict("ENUMS"), ...parseDict("PY_ONLY_ENUMS") };

  it("parsed the expected fields (not vacuous)", () => {
    expect(Object.keys(py).sort()).toEqual(
      [
        "arch", "discipline", "foot_width", "heel_fit", "instep", "level",
        "terrain", "toe_shape",
      ].sort(),
    );
  });

  it("matches every enum vocabulary exactly", () => {
    expect([...ENUM_FIELDS].sort()).toEqual(Object.keys(py).sort());
    for (const field of ENUM_FIELDS) {
      expect([...ENUM_VOCAB[field]].sort(), field).toEqual([...py[field]].sort());
    }
  });

  it("has a label for every option value", () => {
    for (const field of ENUM_FIELDS) {
      for (const value of ENUM_VOCAB[field]) {
        expect(OPTION_LABELS[field][value], `${field}.${value}`).toBeTruthy();
      }
    }
  });

  it("matches the street size bounds", () => {
    const [min, max] = parsePair("STREET_SIZE_MIN", "STREET_SIZE_MAX");
    expect(STREET_SIZE_BOUNDS.minExclusive).toBe(min);
    expect(STREET_SIZE_BOUNDS.max).toBe(max);
    expect(STREET_SIZE_BOUNDS.decimals).toBe(parseConst("STREET_SIZE_DECIMALS"));
  });

  it("matches the budget bounds", () => {
    expect(BUDGET_BOUNDS.minExclusive).toBe(parseConst("BUDGET_MIN_EXCLUSIVE"));
    expect(BUDGET_BOUNDS.limitExclusive).toBe(parseConst("BUDGET_NUMERIC_LIMIT"));
    expect(BUDGET_BOUNDS.decimals).toBe(parseConst("BUDGET_DECIMALS"));
  });

  it("ties the number-input attributes to the schema.py constants", () => {
    const [, max] = parsePair("STREET_SIZE_MIN", "STREET_SIZE_MAX");
    const sDec = parseConst("STREET_SIZE_DECIMALS");
    const bDec = parseConst("BUDGET_DECIMALS");
    const limit = parseConst("BUDGET_NUMERIC_LIMIT");
    expect(STREET_SIZE_INPUT).toEqual({ min: 10 ** -sDec, max, step: 10 ** -sDec });
    const step = 10 ** -bDec;
    expect(BUDGET_INPUT).toEqual({
      min: step,
      max: Number((limit - step).toFixed(bDec)),
      step,
    });
  });

  describe("anchor size rules (anchors.py)", () => {
    const anchors = readFileSync(
      resolve(dirname(fileURLToPath(import.meta.url)), "../../../../backend/app/survey/anchors.py"),
      "utf8",
    );

    it("matches the non-alphanumeric part of SIZE_ALLOWED_CHARS", () => {
      const start = anchors.indexOf("SIZE_ALLOWED_CHARS = frozenset(");
      expect(start).toBeGreaterThan(-1);
      const block = anchors.slice(start, anchors.indexOf("\n)", start));
      const literals = [...block.matchAll(/"((?:[^"\\]|\\.)*)"/g)].map((m) => m[1]);
      expect(literals.length).toBeGreaterThanOrEqual(3);
      const extras = literals
        .map((l) => JSON.parse(`"${l}"`) as string)
        .map((l) => l.replace(/[0-9A-Za-z]/g, ""))
        .join("");
      expect(extras.length).toBeGreaterThan(0);
      expect([...SIZE_ALLOWED_EXTRA].sort()).toEqual([...extras].sort());
    });

    it("matches ANCHOR_SIZE_MAX_LEN", () => {
      const m = anchors.match(/^ANCHOR_SIZE_MAX_LEN\s*=\s*(\d+)/m);
      expect(m).not.toBeNull();
      expect(ANCHOR_SIZE_MAX_LENGTH).toBe(Number(m![1]));
    });
  });

  it("states the number bounds in words", () => {
    expect(STREET_SIZE_HINT).toContain("Between 0.1 and 20, at most one decimal place.");
    expect(BUDGET_HINT).toContain("More than 0 and under 100,000, at most two decimal places.");
  });
});
