import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchQuadrant, fetchRecommendations, fetchShoes, submitSurvey } from "./api";

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

describe("submitSurvey", () => {
  const reply = (status: number, body: unknown) =>
    vi.fn(async () => new Response(JSON.stringify(body), { status }));

  it("returns the survey token from a 201", async () => {
    vi.stubGlobal("fetch", reply(201, { survey_token: "tok-1" }));
    await expect(submitSurvey({})).resolves.toEqual({ kind: "created", surveyToken: "tok-1" });
  });

  it.each([
    ["no token", {}],
    ["an empty token", { survey_token: "" }],
    ["a numeric token", { survey_token: 7 }],
    ["a null body", null],
  ])("treats a 201 with %s as failed", async (_name, body) => {
    vi.stubGlobal("fetch", reply(201, body));
    await expect(submitSurvey({})).resolves.toEqual({ kind: "failed" });
  });
});

describe("fetchRecommendations", () => {
  const shoe = {
    ...good,
    x: 0.5,
    y: -0.2,
    prior_source: "hand",
    is_anchor: false,
    quadrant: "Q1",
    msrp_usd: 180,
    price_unknown: false,
    fit_score: 0.7,
    style_score: 0.9,
    budget_score: null,
    total_score: 0.8,
    confidence: 0.6,
    confidence_label: "medium",
    rank: 1,
    warnings: [],
  };
  const second = { ...shoe, id: "b", rank: 2, msrp_usd: null, price_unknown: true };
  const ranking = {
    scorer_version: "v0-slice",
    target: { x: 0.4, y: -0.1 },
    terms: { fit: true, style: true, budget: false },
    gated_out: { over_budget: 0, size_unavailable: 0, unplaced: 1 },
    warnings: [],
    results: [shoe, second],
  };

  it("returns a well-formed ranking", async () => {
    vi.stubGlobal("fetch", ok(ranking));
    await expect(fetchRecommendations("tok")).resolves.toEqual({ kind: "ranked", ranking });
  });

  it("sends the token in the JSON body to the same-origin route, not the URL", async () => {
    const f = ok(ranking);
    vi.stubGlobal("fetch", f);
    await fetchRecommendations("tok-42");
    const [url, init] = f.mock.calls[0] as unknown as [string, RequestInit];
    expect([url, init.method, JSON.parse(init.body as string)]).toEqual([
      "/api/recommend",
      "POST",
      { survey_token: "tok-42" },
    ]);
  });

  it("passes the abort signal to fetch", async () => {
    const f = ok(ranking);
    vi.stubGlobal("fetch", f);
    const controller = new AbortController();
    await fetchRecommendations("tok", controller.signal);
    expect((f.mock.calls[0] as unknown as [string, RequestInit])[1].signal).toBe(controller.signal);
  });

  it.each([
    ["no target and no results", { ...ranking, target: null, results: [] }],
    ["scores at the bounds", { ...ranking, results: [{ ...shoe, fit_score: 0, total_score: 1 }] }],
  ])("accepts %s", async (_name, body) => {
    vi.stubGlobal("fetch", ok(body));
    await expect(fetchRecommendations("tok")).resolves.toEqual({ kind: "ranked", ranking: body });
  });

  it.each([404, 422])("answers survey-not-found for a %i", async (status) => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json({ errors: ["survey not found"] }, { status })),
    );
    await expect(fetchRecommendations("tok")).resolves.toEqual({ kind: "survey-not-found" });
  });

  it("rejects a 502 with its status", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json({ errors: ["unavailable"] }, { status: 502 })),
    );
    await expect(fetchRecommendations("tok")).rejects.toThrow("(502)");
  });

  it.each([
    ["not an object", []],
    ["a missing scorer_version", { ...ranking, scorer_version: undefined }],
    ["a target off the plane", { ...ranking, target: { x: 1.5, y: 0 } }],
    ["a non-boolean term", { ...ranking, terms: { ...ranking.terms, fit: "yes" } }],
    ["a negative gated count", { ...ranking, gated_out: { ...ranking.gated_out, unplaced: -1 } }],
    ["a fractional gated count", { ...ranking, gated_out: { ...ranking.gated_out, over_budget: 0.5 } }],
    ["non-string survey warnings", { ...ranking, warnings: [1] }],
    ["results not a list", { ...ranking, results: {} }],
    ["a malformed shoe identity", { ...ranking, results: [{ ...shoe, gender: "kids" }] }],
    ["price_unknown true with a price", { ...ranking, results: [{ ...shoe, price_unknown: true }] }],
    ["price_unknown false without a price", { ...ranking, results: [{ ...shoe, msrp_usd: null }] }],
    ["a negative price", { ...ranking, results: [{ ...shoe, msrp_usd: -1 }] }],
    ["a term score above 1", { ...ranking, results: [{ ...shoe, style_score: 1.01 }] }],
    ["a negative term score", { ...ranking, results: [{ ...shoe, fit_score: -0.1 }] }],
    ["a null total", { ...ranking, results: [{ ...shoe, total_score: null }] }],
    ["an out-of-range confidence", { ...ranking, results: [{ ...shoe, confidence: 2 }] }],
    ["an unknown confidence label", { ...ranking, results: [{ ...shoe, confidence_label: "certain" }] }],
    ["ranks not starting at 1", { ...ranking, results: [{ ...shoe, rank: 2 }] }],
    ["ranks out of order", { ...ranking, results: [second, shoe] }],
    ["a duplicate shoe id", { ...ranking, results: [shoe, { ...second, id: shoe.id }] }],
    ["non-string result warnings", { ...ranking, results: [{ ...shoe, warnings: [null] }] }],
  ])("rejects %s", async (_name, body) => {
    vi.stubGlobal("fetch", ok(body));
    await expect(fetchRecommendations("tok")).rejects.toThrow("malformed");
  });
});
