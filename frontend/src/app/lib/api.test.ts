import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, getShoes, submitSurvey } from "./api";

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
