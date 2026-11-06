import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, getQuadrant, getRecommendations, getShoes, submitSurvey } from "./api";

const fetchMock = vi.fn();

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("submitSurvey", () => {
  it("returns the survey token on 201", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ survey_token: "tok-1" }, 201));

    const result = await submitSurvey({ level: "elite" });

    expect(result).toEqual({ ok: true, surveyToken: "tok-1" });
  });

  it("returns server validation errors verbatim on 422", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ errors: ["bad level", "bad budget"] }, 422));

    const result = await submitSurvey({});

    expect(result).toEqual({ ok: false, errors: ["bad level", "bad budget"] });
  });

  it("posts to /api/survey", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ survey_token: "t" }, 201));

    await submitSurvey({});

    expect(fetchMock.mock.calls[0][0]).toBe("/api/survey");
  });

  it("uses the POST method", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ survey_token: "t" }, 201));

    await submitSurvey({});

    expect(fetchMock.mock.calls[0][1].method).toBe("POST");
  });

  it("sends a JSON content-type header", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ survey_token: "t" }, 201));

    await submitSurvey({});

    expect(new Headers(fetchMock.mock.calls[0][1].headers).get("content-type")).toBe(
      "application/json",
    );
  });

  it("sends the payload as the JSON body", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ survey_token: "t" }, 201));

    await submitSurvey({ level: "elite", street_size: 9.5 });

    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      level: "elite",
      street_size: 9.5,
    });
  });

  it("throws ApiError unavailable on 503", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ errors: ["The service is temporarily unavailable."] }, 503),
    );

    await expect(submitSurvey({})).rejects.toMatchObject({ code: "unavailable" });
  });

  it("carries the server's fixed message on 503", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ errors: ["The service is temporarily unavailable."] }, 503),
    );

    await expect(submitSurvey({})).rejects.toHaveProperty("message", "The service is temporarily unavailable.");
  });

  it("throws ApiError timeout on 504", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ errors: ["too slow"] }, 504));

    await expect(submitSurvey({})).rejects.toMatchObject({ code: "timeout" });
  });

  it("throws ApiError unavailable on 502", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ errors: ["unexpected"] }, 502));

    await expect(submitSurvey({})).rejects.toMatchObject({ code: "unavailable" });
  });

  it("throws ApiError unavailable on a network TypeError", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));

    await expect(submitSurvey({})).rejects.toMatchObject({ code: "unavailable" });
  });

  it("throws ApiError rejected on 415", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ errors: ["unsupported"] }, 415));

    await expect(submitSurvey({})).rejects.toMatchObject({ code: "rejected" });
  });

  it("throws ApiError rejected on 413", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ errors: ["too big"] }, 413));

    await expect(submitSurvey({})).rejects.toMatchObject({ code: "rejected" });
  });

  it("throws ApiError bad_response when 201 lacks a token", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ nope: 1 }, 201));

    await expect(submitSurvey({})).rejects.toMatchObject({ code: "bad_response" });
  });

  it("throws ApiError bad_response when 422 lacks an errors array", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ errors: "text" }, 422));

    await expect(submitSurvey({})).rejects.toMatchObject({ code: "bad_response" });
  });

  it("throws ApiError bad_response on an unlisted status", async () => {
    fetchMock.mockResolvedValue(new Response("", { status: 302 }));

    await expect(submitSurvey({})).rejects.toMatchObject({ code: "bad_response" });
  });

  it("throws an ApiError instance on 503", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ errors: ["down"] }, 503));

    await expect(submitSurvey({})).rejects.toBeInstanceOf(ApiError);
  });

  it("keeps the original TypeError as the cause of a network failure", async () => {
    const networkError = new TypeError("Failed to fetch");
    fetchMock.mockRejectedValue(networkError);

    await expect(submitSurvey({})).rejects.toHaveProperty("cause", networkError);
  });

  it("carries the server's fixed message on 504", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ errors: ["The service took too long to respond."] }, 504),
    );

    await expect(submitSurvey({})).rejects.toHaveProperty(
      "message",
      "The service took too long to respond.",
    );
  });

  it("throws ApiError rejected on 400", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ errors: ["bad request"] }, 400));

    await expect(submitSurvey({})).rejects.toMatchObject({ code: "rejected" });
  });

  it("throws ApiError bad_response on 500", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ errors: ["boom"] }, 500));

    await expect(submitSurvey({})).rejects.toMatchObject({ code: "bad_response" });
  });

  it("falls back to a fixed message when the error body has no errors array", async () => {
    fetchMock.mockResolvedValue(new Response("not json", { status: 503 }));

    await expect(submitSurvey({})).rejects.toHaveProperty(
      "message",
      "The service is temporarily unavailable.",
    );
  });

  it("throws ApiError bad_response on a non-JSON 201 body", async () => {
    fetchMock.mockResolvedValue(new Response("<html>", { status: 201 }));

    await expect(submitSurvey({})).rejects.toMatchObject({ code: "bad_response" });
  });

  it("throws ApiError bad_response on a non-JSON 422 body", async () => {
    fetchMock.mockResolvedValue(new Response("<html>", { status: 422 }));

    await expect(submitSurvey({})).rejects.toMatchObject({ code: "bad_response" });
  });
});

describe("getShoes", () => {
  it("returns the shoe list on 200", async () => {
    const shoes = [{ id: "1", brand: "La Sportiva", model: "Solution", version: "", gender: "unisex" }];
    fetchMock.mockResolvedValue(jsonResponse(shoes, 200));

    expect(await getShoes()).toEqual(shoes);
  });

  it("requests /api/shoes with GET", async () => {
    fetchMock.mockResolvedValue(jsonResponse([], 200));

    await getShoes();

    expect(fetchMock.mock.calls[0][0]).toBe("/api/shoes");
  });

  it("throws ApiError bad_response on a non-JSON 200 body", async () => {
    fetchMock.mockResolvedValue(new Response("<html>", { status: 200 }));

    await expect(getShoes()).rejects.toMatchObject({ code: "bad_response" });
  });

  it("throws ApiError bad_response when a shoe element is malformed", async () => {
    fetchMock.mockResolvedValue(jsonResponse([{ id: "1", brand: "La Sportiva" }], 200));

    await expect(getShoes()).rejects.toMatchObject({ code: "bad_response" });
  });

  it("throws ApiError bad_response when a shoe has an unknown gender", async () => {
    const shoe = { id: "1", brand: "b", model: "m", version: "", gender: "kids" };
    fetchMock.mockResolvedValue(jsonResponse([shoe], 200));

    await expect(getShoes()).rejects.toMatchObject({ code: "bad_response" });
  });

  it("throws ApiError bad_response when 200 body is not an array", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ shoes: [] }, 200));

    await expect(getShoes()).rejects.toMatchObject({ code: "bad_response" });
  });

  it("throws ApiError unavailable on 503", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ errors: ["down"] }, 503));

    await expect(getShoes()).rejects.toMatchObject({ code: "unavailable" });
  });

  it("throws ApiError unavailable on a network TypeError", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));

    await expect(getShoes()).rejects.toMatchObject({ code: "unavailable" });
  });
});

describe("getQuadrant", () => {
  const validShoe = {
    id: "1",
    brand: "La Sportiva",
    model: "Solution",
    version: "",
    gender: "unisex",
    x: 0.4,
    y: -0.6,
    prior_source: "corpus",
    is_anchor: true,
    quadrant: "Q4",
  };

  it("returns the quadrant list on 200", async () => {
    fetchMock.mockResolvedValue(jsonResponse([validShoe], 200));

    expect(await getQuadrant()).toEqual([validShoe]);
  });

  it("requests /api/quadrant", async () => {
    fetchMock.mockResolvedValue(jsonResponse([], 200));

    await getQuadrant();

    expect(fetchMock.mock.calls[0][0]).toBe("/api/quadrant");
  });

  it("throws ApiError bad_response when 200 body is not an array", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ shoes: [] }, 200));

    await expect(getQuadrant()).rejects.toMatchObject({ code: "bad_response" });
  });

  it("throws ApiError bad_response when x is a string", async () => {
    fetchMock.mockResolvedValue(jsonResponse([{ ...validShoe, x: "0.4" }], 200));

    await expect(getQuadrant()).rejects.toMatchObject({ code: "bad_response" });
  });

  it("throws ApiError bad_response when x is outside [-1, 1]", async () => {
    fetchMock.mockResolvedValue(jsonResponse([{ ...validShoe, x: 1.5 }], 200));

    await expect(getQuadrant()).rejects.toMatchObject({ code: "bad_response" });
  });

  it("accepts x at the inclusive upper bound 1", async () => {
    const shoe = { ...validShoe, x: 1 };
    fetchMock.mockResolvedValue(jsonResponse([shoe], 200));

    expect(await getQuadrant()).toEqual([shoe]);
  });

  it("accepts y at the inclusive lower bound -1", async () => {
    const shoe = { ...validShoe, y: -1 };
    fetchMock.mockResolvedValue(jsonResponse([shoe], 200));

    expect(await getQuadrant()).toEqual([shoe]);
  });

  it("throws ApiError bad_response when y is missing", async () => {
    const withoutY: Record<string, unknown> = { ...validShoe };
    delete withoutY.y;
    fetchMock.mockResolvedValue(jsonResponse([withoutY], 200));

    await expect(getQuadrant()).rejects.toMatchObject({ code: "bad_response" });
  });

  it("throws ApiError bad_response on an unknown prior_source", async () => {
    fetchMock.mockResolvedValue(jsonResponse([{ ...validShoe, prior_source: "guess" }], 200));

    await expect(getQuadrant()).rejects.toMatchObject({ code: "bad_response" });
  });

  it("throws ApiError bad_response when is_anchor is not a boolean", async () => {
    fetchMock.mockResolvedValue(jsonResponse([{ ...validShoe, is_anchor: "yes" }], 200));

    await expect(getQuadrant()).rejects.toMatchObject({ code: "bad_response" });
  });

  it("throws ApiError bad_response on quadrant ON-AXIS", async () => {
    fetchMock.mockResolvedValue(jsonResponse([{ ...validShoe, quadrant: "ON-AXIS" }], 200));

    await expect(getQuadrant()).rejects.toMatchObject({ code: "bad_response" });
  });

  it("throws ApiError unavailable on 503", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ errors: ["down"] }, 503));

    await expect(getQuadrant()).rejects.toMatchObject({ code: "unavailable" });
  });

  it("throws ApiError timeout on 504", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ errors: ["slow"] }, 504));

    await expect(getQuadrant()).rejects.toMatchObject({ code: "timeout" });
  });

  it("throws ApiError unavailable on a network TypeError", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));

    await expect(getQuadrant()).rejects.toMatchObject({ code: "unavailable" });
  });
});

describe("getRecommendations", () => {
  const validRecommendation = {
    id: "1",
    brand: "La Sportiva",
    model: "Solution",
    version: "",
    gender: "unisex",
    x: 0.4,
    y: -0.6,
    prior_source: "corpus",
    is_anchor: false,
    quadrant: "Q4",
    msrp_usd: 190,
    price_unknown: false,
    fit_score: 0.8,
    style_score: 0.5,
    budget_score: null,
    total_score: 0.7,
    confidence: 0.9,
    confidence_label: "high",
    rank: 1,
    warnings: [],
  };
  const validRanking = {
    scorer_version: "v1",
    target: { x: 0.2, y: -0.3 },
    terms: { fit: true, style: true, budget: false },
    gated_out: { over_budget: 0, size_unavailable: 1, unplaced: 2 },
    warnings: [],
    results: [validRecommendation],
  };

  function rankingWith(result: Record<string, unknown>) {
    return { ...validRanking, results: [{ ...validRecommendation, ...result }] };
  }

  it("sends only the survey token in the JSON body", async () => {
    fetchMock.mockResolvedValue(jsonResponse(validRanking, 200));

    await getRecommendations("tok-1");

    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ survey_token: "tok-1" });
  });

  it("posts to exactly /api/recommend with no token in the URL", async () => {
    fetchMock.mockResolvedValue(jsonResponse(validRanking, 200));

    await getRecommendations("tok-1");

    expect(fetchMock.mock.calls[0][0]).toBe("/api/recommend");
  });

  it("uses the POST method", async () => {
    fetchMock.mockResolvedValue(jsonResponse(validRanking, 200));

    await getRecommendations("tok-1");

    expect(fetchMock.mock.calls[0][1].method).toBe("POST");
  });

  it("sends a JSON content-type header", async () => {
    fetchMock.mockResolvedValue(jsonResponse(validRanking, 200));

    await getRecommendations("tok-1");

    expect(fetchMock.mock.calls[0][1].headers).toEqual({ "content-type": "application/json" });
  });

  it("returns the ranking on a valid 200", async () => {
    fetchMock.mockResolvedValue(jsonResponse(validRanking, 200));

    expect(await getRecommendations("tok-1")).toEqual({ status: "ok", ranking: validRanking });
  });

  it("returns survey_not_found on 404", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ errors: ["not found"] }, 404));

    expect(await getRecommendations("tok-1")).toEqual({ status: "survey_not_found" });
  });

  it("returns survey_not_found on 422 because a malformed token can never match", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ errors: ["bad token"] }, 422));

    expect(await getRecommendations("nope")).toEqual({ status: "survey_not_found" });
  });

  it("throws ApiError unavailable on 502", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ errors: ["bad gateway"] }, 502));

    await expect(getRecommendations("tok-1")).rejects.toMatchObject({ code: "unavailable" });
  });

  it("throws ApiError timeout on 504", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ errors: ["slow"] }, 504));

    await expect(getRecommendations("tok-1")).rejects.toMatchObject({ code: "timeout" });
  });

  it("throws ApiError bad_response on a non-JSON 200", async () => {
    fetchMock.mockResolvedValue(new Response("<html>", { status: 200 }));

    await expect(getRecommendations("tok-1")).rejects.toMatchObject({ code: "bad_response" });
  });

  it("throws bad_response on an unknown confidence_label", async () => {
    fetchMock.mockResolvedValue(jsonResponse(rankingWith({ confidence_label: "certain" }), 200));

    await expect(getRecommendations("tok-1")).rejects.toMatchObject({ code: "bad_response" });
  });

  it("throws bad_response when price_unknown is true but msrp_usd is a number", async () => {
    fetchMock.mockResolvedValue(jsonResponse(rankingWith({ price_unknown: true }), 200));

    await expect(getRecommendations("tok-1")).rejects.toMatchObject({ code: "bad_response" });
  });

  it("throws bad_response on a negative msrp_usd", async () => {
    fetchMock.mockResolvedValue(jsonResponse(rankingWith({ msrp_usd: -1 }), 200));

    await expect(getRecommendations("tok-1")).rejects.toMatchObject({ code: "bad_response" });
  });

  it("throws bad_response when fit_score is above 1", async () => {
    fetchMock.mockResolvedValue(jsonResponse(rankingWith({ fit_score: 1.2 }), 200));

    await expect(getRecommendations("tok-1")).rejects.toMatchObject({ code: "bad_response" });
  });

  it("throws bad_response on a non-integer rank", async () => {
    fetchMock.mockResolvedValue(jsonResponse(rankingWith({ rank: 1.5 }), 200));

    await expect(getRecommendations("tok-1")).rejects.toMatchObject({ code: "bad_response" });
  });

  it("throws bad_response when ranks are out of order", async () => {
    const second = { ...validRecommendation, id: "2", rank: 1 };
    const body = { ...validRanking, results: [validRecommendation, second] };
    fetchMock.mockResolvedValue(jsonResponse(body, 200));

    await expect(getRecommendations("tok-1")).rejects.toMatchObject({ code: "bad_response" });
  });

  it("throws bad_response when target x is 1.5", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ...validRanking, target: { x: 1.5, y: 0 } }, 200));

    await expect(getRecommendations("tok-1")).rejects.toMatchObject({ code: "bad_response" });
  });

  it("throws bad_response on a negative gated_out count", async () => {
    const gatedOut = { ...validRanking.gated_out, over_budget: -1 };
    fetchMock.mockResolvedValue(jsonResponse({ ...validRanking, gated_out: gatedOut }, 200));

    await expect(getRecommendations("tok-1")).rejects.toMatchObject({ code: "bad_response" });
  });

  it("throws bad_response on a non-string warning", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ...validRanking, warnings: [3] }, 200));

    await expect(getRecommendations("tok-1")).rejects.toMatchObject({ code: "bad_response" });
  });

  it("throws bad_response when terms.budget is missing", async () => {
    const terms = { fit: true, style: true };
    fetchMock.mockResolvedValue(jsonResponse({ ...validRanking, terms }, 200));

    await expect(getRecommendations("tok-1")).rejects.toMatchObject({ code: "bad_response" });
  });

  it("accepts an empty results list", async () => {
    const body = { ...validRanking, results: [] };
    fetchMock.mockResolvedValue(jsonResponse(body, 200));

    expect(await getRecommendations("tok-1")).toEqual({ status: "ok", ranking: body });
  });

  it("throws bad_response on duplicate shoe ids", async () => {
    const second = { ...validRecommendation, rank: 2 };
    const body = { ...validRanking, results: [validRecommendation, second] };
    fetchMock.mockResolvedValue(jsonResponse(body, 200));

    await expect(getRecommendations("tok-1")).rejects.toMatchObject({ code: "bad_response" });
  });

  it("passes the abort signal to fetch", async () => {
    fetchMock.mockResolvedValue(jsonResponse(validRanking, 200));
    const controller = new AbortController();

    await getRecommendations("tok-1", controller.signal);

    expect(fetchMock.mock.calls[0][1].signal).toBe(controller.signal);
  });

  it("accepts a null target", async () => {
    const body = { ...validRanking, target: null };
    fetchMock.mockResolvedValue(jsonResponse(body, 200));

    expect(await getRecommendations("tok-1")).toEqual({ status: "ok", ranking: body });
  });
});
