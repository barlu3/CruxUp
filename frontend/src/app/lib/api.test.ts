import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchQuadrant, fetchShoes } from "./api";

const ok = (body: unknown) =>
  vi.fn(async () => new Response(JSON.stringify(body), { status: 200 }));
const good = { id: "a", brand: "B", model: "M", version: "", gender: "unisex" };

afterEach(() => vi.unstubAllGlobals());

describe("fetchShoes validation", () => {
  it("accepts well-formed rows", async () => {
    vi.stubGlobal("fetch", ok([good]));
    await expect(fetchShoes()).resolves.toEqual([good]);
  });

  it.each([
    ["not an array", { shoes: [] }],
    ["non-string id", [{ ...good, id: 1 }]],
    ["missing brand", [{ ...good, brand: undefined }]],
    ["null version", [{ ...good, version: null }]],
    ["unknown gender", [{ ...good, gender: "kids" }]],
    ["a null row", [good, null]],
  ])("rejects %s", async (_name, body) => {
    vi.stubGlobal("fetch", ok(body));
    await expect(fetchShoes()).rejects.toThrow();
  });

  it("passes the abort signal to fetch", async () => {
    const f = ok([good]);
    vi.stubGlobal("fetch", f);
    const controller = new AbortController();
    await fetchShoes(controller.signal);
    expect((f.mock.calls[0] as unknown as [string, RequestInit])[1].signal).toBe(controller.signal);
  });
});

describe("fetchQuadrant validation", () => {
  const placed = {
    ...good,
    x: 0.8,
    y: -0.4,
    prior_source: "hand",
    is_anchor: true,
    quadrant: "Q1",
  };

  it("accepts well-formed rows", async () => {
    vi.stubGlobal("fetch", ok([placed]));
    await expect(fetchQuadrant()).resolves.toEqual([placed]);
  });

  it("requests the same-origin /api/quadrant route", async () => {
    const f = ok([]);
    vi.stubGlobal("fetch", f);
    await fetchQuadrant();
    expect((f.mock.calls[0] as unknown as [string])[0]).toBe("/api/quadrant");
  });

  it.each([
    ["x at the upper bound", { ...placed, x: 1 }],
    ["y at the lower bound", { ...placed, y: -1 }],
    ["a spec-derived non-anchor", { ...placed, prior_source: "spec", is_anchor: false }],
  ])("accepts %s", async (_name, row) => {
    vi.stubGlobal("fetch", ok([row]));
    await expect(fetchQuadrant()).resolves.toEqual([row]);
  });

  it.each([
    ["not an array", { shoes: [] }],
    ["a malformed identity", [{ ...placed, gender: "kids" }]],
    ["a string x", [{ ...placed, x: "0.8" }]],
    ["x above 1", [{ ...placed, x: 1.5 }]],
    ["y below -1", [{ ...placed, y: -1.001 }]],
    ["a missing y", [{ ...placed, y: undefined }]],
    ["an unknown prior_source", [{ ...placed, prior_source: "guess" }]],
    ["a string is_anchor", [{ ...placed, is_anchor: "yes" }]],
    ["an on-axis quadrant", [{ ...placed, quadrant: "ON-AXIS" }]],
    ["a null row", [placed, null]],
  ])("rejects %s", async (_name, body) => {
    vi.stubGlobal("fetch", ok(body));
    await expect(fetchQuadrant()).rejects.toThrow();
  });

  it("rejects a non-2xx answer with its status", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json({ errors: ["unavailable"] }, { status: 502 })),
    );
    await expect(fetchQuadrant()).rejects.toThrow("(502)");
  });

  it("passes the abort signal to fetch", async () => {
    const f = ok([placed]);
    vi.stubGlobal("fetch", f);
    const controller = new AbortController();
    await fetchQuadrant(controller.signal);
    expect((f.mock.calls[0] as unknown as [string, RequestInit])[1].signal).toBe(controller.signal);
  });
});
