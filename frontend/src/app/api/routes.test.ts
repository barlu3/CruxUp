// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GET as getQuadrant } from "./quadrant/route";
import { POST as postRecommend } from "./recommend/route";
import { GET as getShoes } from "./shoes/route";
import { POST as postSurvey } from "./survey/route";
import { MAX_SURVEY_BODY_BYTES, callBackend } from "./_lib/backend";
import * as quadrantModule from "./quadrant/route";
import * as recommendModule from "./recommend/route";
import * as shoesModule from "./shoes/route";
import * as surveyModule from "./survey/route";

const fetchMock = vi.fn();
const SHOES_UNAVAILABLE = "The catalogue service is unavailable. Please try again later.";
const SURVEY_UNAVAILABLE = "The survey service is unavailable. Please try again later.";
const QUADRANT_UNAVAILABLE = "The quadrant service is unavailable. Please try again later.";
const RECOMMEND_UNAVAILABLE = "The results service is unavailable. Please try again later.";

const upstream = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  vi.stubEnv("CRUXUP_API_URL", "");
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

const post = (body: BodyInit | null, headers: Record<string, string> = {}) =>
  new Request("http://localhost:3000/api/survey", {
    method: "POST",
    body,
    headers: { "content-type": "application/json", ...headers },
  });

function chunkedBody(chunks: Uint8Array[]): ReadableStream<Uint8Array> {
  let i = 0;
  return new ReadableStream({
    pull(controller) {
      if (i < chunks.length) controller.enqueue(chunks[i++]);
      else controller.close();
    },
  });
}

describe("route surface", () => {
  it("does not use the removed segment-config dynamic export", () => {
    expect(shoesModule).not.toHaveProperty("dynamic");
    expect(surveyModule).not.toHaveProperty("dynamic");
    expect(quadrantModule).not.toHaveProperty("dynamic");
    expect(recommendModule).not.toHaveProperty("dynamic");
  });

  it("exports exactly GET on /api/shoes and /api/quadrant and POST on /api/survey and /api/recommend", () => {
    const methods = /^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)$/;
    expect(Object.keys(shoesModule).filter((k) => methods.test(k))).toEqual(["GET"]);
    expect(Object.keys(quadrantModule).filter((k) => methods.test(k))).toEqual(["GET"]);
    expect(Object.keys(surveyModule).filter((k) => methods.test(k))).toEqual(["POST"]);
    expect(Object.keys(recommendModule).filter((k) => methods.test(k))).toEqual(["POST"]);
  });
});

describe("callBackend allow-list", () => {
  it.each(["/docs", "/openapi.json", "/recommend/", "/shoes/", "/survey?x=1", "//evil.test/shoes"])(
    "refuses %s without contacting upstream",
    (path) => {
      expect(() => callBackend(path, { method: "GET" })).toThrow("not allow-listed");
      expect(fetchMock).not.toHaveBeenCalled();
    },
  );
});

describe("GET /api/shoes", () => {
  it("calls the default backend when CRUXUP_API_URL is unset", async () => {
    fetchMock.mockResolvedValue(upstream(200, []));
    await getShoes();
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe("http://127.0.0.1:8000/shoes");
    expect(init.method ?? "GET").toBe("GET");
    expect(init.cache).toBe("no-store");
    expect(init.signal).toBeInstanceOf(AbortSignal);
    expect(init.headers).toEqual({ accept: "application/json" });
  });

  it("reads CRUXUP_API_URL on every call and tolerates a trailing slash", async () => {
    fetchMock.mockImplementation(async () => upstream(200, []));
    vi.stubEnv("CRUXUP_API_URL", "http://api.test:9000/");
    await getShoes();
    vi.stubEnv("CRUXUP_API_URL", "http://other.test");
    await getShoes();
    expect(String(fetchMock.mock.calls[0][0])).toBe("http://api.test:9000/shoes");
    expect(String(fetchMock.mock.calls[1][0])).toBe("http://other.test/shoes");
  });

  it("passes status 200 and body through", async () => {
    fetchMock.mockResolvedValue(upstream(200, [{ id: "1" }]));
    const res = await getShoes();
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toContain("application/json");
    expect(await res.json()).toEqual([{ id: "1" }]);
  });

  it.each([
    [503, { detail: "database unavailable" }],
    [500, { detail: "could not complete the request" }],
    [404, { detail: "Not Found" }],
    [201, []],
  ])("masks upstream status %i as a 502 with the fixed envelope", async (status, body) => {
    fetchMock.mockResolvedValue(upstream(status, body));
    const res = await getShoes();
    expect(res.status).toBe(502);
    expect(res.headers.get("content-type")).toContain("application/json");
    expect(await res.json()).toEqual({ errors: [SHOES_UNAVAILABLE] });
  });

  it("refuses redirects and turns the resulting throw into the 502 envelope", async () => {
    fetchMock.mockRejectedValue(new TypeError("fetch failed: unexpected redirect"));
    const res = await getShoes();
    expect(fetchMock.mock.calls[0][1].redirect).toBe("error");
    expect(res.status).toBe(502);
  });

  it("answers 502 when the upstream fetch throws", async () => {
    fetchMock.mockRejectedValue(new TypeError("fetch failed"));
    const res = await getShoes();
    expect(res.status).toBe(502);
    expect(await res.json()).toEqual({ errors: [SHOES_UNAVAILABLE] });
  });
});

describe("POST /api/survey", () => {
  it("forwards the raw body unchanged with only the two fixed headers", async () => {
    fetchMock.mockResolvedValue(upstream(201, { survey_token: "abc" }));
    const raw = '{"instep": "low", not even json';
    const res = await postSurvey(
      post(raw, {
        "content-type": "application/json",
        cookie: "session=secret",
        authorization: "Bearer secret",
        "x-forwarded-for": "1.2.3.4",
      }),
    );
    expect(res.status).toBe(201);
    expect(await res.json()).toEqual({ survey_token: "abc" });
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe("http://127.0.0.1:8000/survey");
    expect(init.method).toBe("POST");
    expect(init.cache).toBe("no-store");
    expect(init.signal).toBeInstanceOf(AbortSignal);
    expect(init.headers).toEqual({
      accept: "application/json",
      "content-type": "application/json",
    });
    const sent = init.body instanceof Uint8Array ? new TextDecoder().decode(init.body) : init.body;
    expect(sent).toBe(raw);
  });

  it("uses CRUXUP_API_URL read at request time", async () => {
    fetchMock.mockResolvedValue(upstream(201, { survey_token: "a" }));
    vi.stubEnv("CRUXUP_API_URL", "http://api.test:9000/");
    await postSurvey(post("{}"));
    expect(String(fetchMock.mock.calls[0][0])).toBe("http://api.test:9000/survey");
  });

  it.each([
    [201, { survey_token: "abc" }],
    [422, { errors: ["bad <b>x</b>"] }],
  ])("passes status %i and body through", async (status, body) => {
    fetchMock.mockResolvedValue(upstream(status, body));
    const res = await postSurvey(post("{}"));
    expect(res.status).toBe(status);
    expect(res.headers.get("content-type")).toContain("application/json");
    expect(await res.json()).toEqual(body);
  });

  it.each([
    [503, { detail: "database unavailable" }],
    [500, { detail: "Traceback (most recent call last): secret" }],
    [400, { detail: "bad request" }],
    [200, { survey_token: "abc" }],
  ])("masks upstream status %i as a 502 with the fixed envelope", async (status, body) => {
    fetchMock.mockResolvedValue(upstream(status, body));
    const res = await postSurvey(post("{}"));
    expect(res.status).toBe(502);
    expect(await res.json()).toEqual({ errors: [SURVEY_UNAVAILABLE] });
  });

  it("accepts a body of exactly the cap", async () => {
    fetchMock.mockResolvedValue(upstream(201, { survey_token: "a" }));
    const res = await postSurvey(post("x".repeat(MAX_SURVEY_BODY_BYTES)));
    expect(res.status).toBe(201);
  });

  it("answers 413 for an oversized content-length without contacting upstream", async () => {
    const res = await postSurvey(
      post("{}", { "content-length": String(MAX_SURVEY_BODY_BYTES + 1) }),
    );
    expect(res.status).toBe(413);
    expect(await res.json()).toEqual({ errors: ["request body exceeds 65536 bytes"] });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("answers 413 for a streamed body that outgrows a lying content-length", async () => {
    const big = new Uint8Array(40_000).fill(120);
    const req = new Request("http://localhost:3000/api/survey", {
      method: "POST",
      body: chunkedBody([big, big, big]),
      headers: { "content-length": "10", "content-type": "application/json" },
      // @ts-expect-error duplex is required by Node for stream bodies
      duplex: "half",
    });
    const res = await postSurvey(req);
    expect(res.status).toBe(413);
    expect(await res.json()).toEqual({ errors: ["request body exceeds 65536 bytes"] });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects a non-JSON content type with 415 and no upstream call", async () => {
    const res = await postSurvey(post("{}", { "content-type": "text/plain" }));
    expect(res.status).toBe(415);
    expect(await res.json()).toEqual({
      errors: ["request body must be JSON (content-type: application/json)"],
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects a missing content type with 415", async () => {
    const req = new Request("http://localhost:3000/api/survey", {
      method: "POST",
      body: new Uint8Array([123, 125]),
    });
    req.headers.delete("content-type");
    const res = await postSurvey(req);
    expect(res.status).toBe(415);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each([
    "application/json; charset=utf-8",
    "APPLICATION/JSON",
    "application/vnd.api+json",
    "application/merge-patch+JSON; x=y",
  ])("forwards content type %s", async (ct) => {
    fetchMock.mockResolvedValue(upstream(201, { survey_token: "a" }));
    const res = await postSurvey(post("{}", { "content-type": ct }));
    expect(res.status).toBe(201);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it.each(["application/jsonx", "text/json", "application/x-www-form-urlencoded", "multipart/form-data; boundary=a"])(
    "rejects content type %s",
    async (ct) => {
      const res = await postSurvey(post("{}", { "content-type": ct }));
      expect(res.status).toBe(415);
    },
  );

  it("forwards an empty body", async () => {
    fetchMock.mockResolvedValue(upstream(422, { errors: ["request body is not valid JSON"] }));
    const res = await postSurvey(post(null));
    expect(res.status).toBe(422);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("refuses redirects and turns the resulting throw into the 502 envelope", async () => {
    fetchMock.mockRejectedValue(new TypeError("fetch failed: unexpected redirect"));
    const res = await postSurvey(post("{}"));
    expect(fetchMock.mock.calls[0][1].redirect).toBe("error");
    expect(res.status).toBe(502);
  });

  it("counts bytes, not characters, at the cap", async () => {
    fetchMock.mockResolvedValue(upstream(201, { survey_token: "a" }));
    const exact = "\u00e9".repeat(32_768); // 2 bytes each = 65,536 bytes
    const res = await postSurvey(post(exact));
    expect(res.status).toBe(201);
    const sent = fetchMock.mock.calls[0][1].body as Uint8Array;
    expect(sent.byteLength).toBe(65_536);
    expect(new TextDecoder().decode(sent)).toBe(exact);

    fetchMock.mockClear();
    const over = await postSurvey(post("\u00e9".repeat(32_769)));
    expect(over.status).toBe(413);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("answers 502 when the upstream fetch throws", async () => {
    fetchMock.mockRejectedValue(new DOMException("timed out", "TimeoutError"));
    const res = await postSurvey(post("{}"));
    expect(res.status).toBe(502);
    expect(await res.json()).toEqual({ errors: [SURVEY_UNAVAILABLE] });
  });
});

describe("GET /api/quadrant", () => {
  it("calls the backend's /quadrant with GET and only the accept header", async () => {
    fetchMock.mockResolvedValue(upstream(200, []));
    await getQuadrant();
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe("http://127.0.0.1:8000/quadrant");
    expect(init.method).toBe("GET");
    expect(init.cache).toBe("no-store");
    expect(init.redirect).toBe("error");
    expect(init.headers).toEqual({ accept: "application/json" });
  });

  it("passes status 200 and the list through unchanged", async () => {
    const body = [{ id: "1", x: 0.5, y: -0.5 }];
    fetchMock.mockResolvedValue(upstream(200, body));
    const res = await getQuadrant();
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual(body);
  });

  it.each([
    [500, { detail: "could not complete the request" }],
    [503, { detail: "database unavailable" }],
    [404, { detail: "Not Found" }],
  ])("masks upstream status %i as a 502 with the fixed envelope", async (status, body) => {
    fetchMock.mockResolvedValue(upstream(status, body));
    const res = await getQuadrant();
    expect(res.status).toBe(502);
    expect(await res.json()).toEqual({ errors: [QUADRANT_UNAVAILABLE] });
  });

  it("answers 502 when the upstream fetch throws", async () => {
    fetchMock.mockRejectedValue(new DOMException("timed out", "TimeoutError"));
    const res = await getQuadrant();
    expect(res.status).toBe(502);
    expect(await res.json()).toEqual({ errors: [QUADRANT_UNAVAILABLE] });
  });
});

describe("POST /api/recommend", () => {
  const SECRET_TOKEN = "tok-SECRET-7f3a9c";
  const postTo = (body: BodyInit | null, headers: Record<string, string> = {}) =>
    new Request("http://localhost:3000/api/recommend", {
      method: "POST",
      body,
      headers: { "content-type": "application/json", ...headers },
    });

  it("forwards the raw body to /recommend with only the two fixed headers", async () => {
    fetchMock.mockResolvedValue(upstream(200, { results: [] }));
    const raw = JSON.stringify({ survey_token: SECRET_TOKEN });
    await postRecommend(postTo(raw, { cookie: "session=secret", authorization: "Bearer x" }));
    const [url, init] = fetchMock.mock.calls[0];
    expect([String(url), init.method, init.redirect, init.headers, new TextDecoder().decode(init.body)]).toEqual([
      "http://127.0.0.1:8000/recommend",
      "POST",
      "error",
      { accept: "application/json", "content-type": "application/json" },
      raw,
    ]);
  });

  it("passes a 200 body through unchanged", async () => {
    const body = { scorer_version: "v0-slice", results: [] };
    fetchMock.mockResolvedValue(upstream(200, body));
    const res = await postRecommend(postTo("{}"));
    expect([res.status, await res.json()]).toEqual([200, body]);
  });

  it.each([
    [404, "survey not found"],
    [422, "The survey token was not accepted."],
  ])("keeps upstream status %i but replaces its body with a fixed message", async (status, message) => {
    fetchMock.mockResolvedValue(upstream(status, { errors: ["no survey for UPSTREAM-MARKER"] }));
    const res = await postRecommend(postTo("{}"));
    expect([res.status, await res.json()]).toEqual([status, { errors: [message] }]);
  });

  it("cancels the discarded upstream 404 body", async () => {
    const cancel = vi.fn();
    fetchMock.mockResolvedValue(new Response(new ReadableStream({ pull() {}, cancel }), { status: 404 }));
    await postRecommend(postTo("{}"));
    expect(cancel).toHaveBeenCalledTimes(1);
  });

  it.each([
    [500, { detail: "Traceback: secret" }],
    [503, { detail: "database unavailable" }],
    [429, { detail: "slow down" }],
    [401, { detail: "no" }],
    [201, { results: [] }],
  ])("masks upstream status %i as a 502 with the fixed envelope", async (status, body) => {
    fetchMock.mockResolvedValue(upstream(status, body));
    const res = await postRecommend(postTo("{}"));
    expect([res.status, await res.json()]).toEqual([502, { errors: [RECOMMEND_UNAVAILABLE] }]);
  });

  it("answers 502 when the upstream fetch throws", async () => {
    fetchMock.mockRejectedValue(new DOMException("timed out", "TimeoutError"));
    const res = await postRecommend(postTo(JSON.stringify({ survey_token: SECRET_TOKEN })));
    expect([res.status, await res.json()]).toEqual([502, { errors: [RECOMMEND_UNAVAILABLE] }]);
  });

  it("rejects a non-JSON content type with 415 and no upstream call", async () => {
    const res = await postRecommend(postTo("a=b", { "content-type": "application/x-www-form-urlencoded" }));
    expect([res.status, fetchMock.mock.calls.length]).toEqual([415, 0]);
  });

  it("accepts a body of exactly 1 KB", async () => {
    fetchMock.mockResolvedValue(upstream(200, { results: [] }));
    const res = await postRecommend(postTo("x".repeat(1024)));
    expect(res.status).toBe(200);
  });

  it("answers 413 for a body over 1 KB without contacting upstream", async () => {
    const res = await postRecommend(postTo("x".repeat(1025)));
    expect([res.status, await res.json(), fetchMock.mock.calls.length]).toEqual([
      413,
      { errors: ["request body exceeds 1024 bytes"] },
      0,
    ]);
  });

  it("answers 413 for a streamed body that outgrows a lying content-length", async () => {
    const chunk = new Uint8Array(600).fill(120);
    const req = new Request("http://localhost:3000/api/recommend", {
      method: "POST",
      body: chunkedBody([chunk, chunk]),
      headers: { "content-length": "10", "content-type": "application/json" },
      // @ts-expect-error duplex is required by Node for stream bodies
      duplex: "half",
    });
    const res = await postRecommend(req);
    expect([res.status, fetchMock.mock.calls.length]).toEqual([413, 0]);
  });
});
