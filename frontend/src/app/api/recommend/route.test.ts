// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { POST } from "./route";

const MAX_BODY_BYTES = 1024;
const SECRET_TOKEN = "tok-SECRET-7f3a9c";

function stubFetch(response: Response | Error) {
  const fetchMock = vi.fn<typeof fetch>(async () => {
    if (response instanceof Error) throw response;
    return response;
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function jsonResponse(body: string, status: number) {
  return new Response(body, {
    status,
    headers: { "content-type": "application/json" },
  });
}

function postRequest(body: BodyInit, headers: Record<string, string> = {}) {
  return new Request("http://localhost:3000/api/recommend", {
    method: "POST",
    body,
    headers: { "content-type": "application/json", ...headers },
  });
}

function streamingRequest(body: ReadableStream<Uint8Array>) {
  return new Request("http://localhost:3000/api/recommend", {
    method: "POST",
    body,
    headers: { "content-type": "application/json" },
    duplex: "half",
  } as RequestInit);
}

function streamOf(chunks: Uint8Array[]) {
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(chunk);
      controller.close();
    },
  });
}

function erroredStream() {
  return new ReadableStream<Uint8Array>({
    start(controller) {
      controller.error(new Error("client aborted"));
    },
  });
}

beforeEach(() => {
  vi.stubEnv("CRUXUP_API_URL", "http://backend.test:9000");
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe("POST /api/recommend forwarding", () => {
  it("forwards the body byte-for-byte", async () => {
    const fetchMock = stubFetch(jsonResponse("{}", 200));
    const bytes = new Uint8Array([0x7b, 0xff, 0x00, 0xc3, 0x28, 0x7d]);

    await POST(postRequest(bytes));

    expect(new Uint8Array(fetchMock.mock.calls[0][1]!.body as ArrayBuffer)).toEqual(bytes);
  });

  it("sends the request to CRUXUP_API_URL/recommend", async () => {
    const fetchMock = stubFetch(jsonResponse("{}", 200));

    await POST(postRequest("{}"));

    expect(fetchMock.mock.calls[0][0]).toBe("http://backend.test:9000/recommend");
  });

  it("uses POST towards the backend", async () => {
    const fetchMock = stubFetch(jsonResponse("{}", 200));

    await POST(postRequest("{}"));

    expect(fetchMock.mock.calls[0][1]?.method).toBe("POST");
  });

  it("forwards only the content-type header", async () => {
    const fetchMock = stubFetch(jsonResponse("{}", 200));

    await POST(
      postRequest("{}", { cookie: "session=secret", authorization: "Bearer x" }),
    );

    expect(Object.fromEntries(new Headers(fetchMock.mock.calls[0][1]!.headers))).toEqual({
      "content-type": "application/json",
    });
  });

  it("refuses to follow upstream redirects", async () => {
    const fetchMock = stubFetch(jsonResponse("{}", 200));

    await POST(postRequest("{}"));

    expect(fetchMock.mock.calls[0][1]?.redirect).toBe("error");
  });
});

describe("POST /api/recommend content type", () => {
  it("returns 415 for a non-JSON content type", async () => {
    stubFetch(jsonResponse("{}", 200));

    const res = await POST(postRequest("a=b", { "content-type": "text/plain" }));

    expect(res.status).toBe(415);
  });

  it("returns 415 when the content type is missing", async () => {
    stubFetch(jsonResponse("{}", 200));
    const req = new Request("http://localhost:3000/api/recommend", {
      method: "POST",
      body: new Uint8Array([1]),
    });

    const res = await POST(req);

    expect(res.status).toBe(415);
  });
});

describe("POST /api/recommend body cap", () => {
  it("returns 413 when Content-Length exceeds 1 KB", async () => {
    stubFetch(jsonResponse("{}", 200));

    const res = await POST(
      postRequest("{}", { "content-length": String(MAX_BODY_BYTES + 1) }),
    );

    expect(res.status).toBe(413);
  });

  it("returns 413 for an oversize streamed body without Content-Length", async () => {
    stubFetch(jsonResponse("{}", 200));
    const chunk = new Uint8Array(MAX_BODY_BYTES / 2 + 1);

    const res = await POST(streamingRequest(streamOf([chunk, chunk])));

    expect(res.status).toBe(413);
  });

  it("accepts a body of exactly 1 KB", async () => {
    stubFetch(jsonResponse("{}", 200));

    const res = await POST(postRequest("x".repeat(MAX_BODY_BYTES)));

    expect(res.status).toBe(200);
  });

  it("returns 400 when the client aborts mid-body", async () => {
    stubFetch(jsonResponse("{}", 200));

    const res = await POST(streamingRequest(erroredStream()));

    expect(res.status).toBe(400);
  });
});

describe("POST /api/recommend upstream responses", () => {
  it("passes a 200 body through unchanged", async () => {
    const body = '{"scorer_version":"v1","results":[]}';
    stubFetch(jsonResponse(body, 200));

    const res = await POST(postRequest("{}"));

    expect(await res.text()).toBe(body);
  });

  it("passes a 404 status through", async () => {
    stubFetch(jsonResponse('{"errors":["survey not found"]}', 404));

    const res = await POST(postRequest("{}"));

    expect(res.status).toBe(404);
  });

  it("replaces the upstream 404 body with the fixed envelope", async () => {
    stubFetch(jsonResponse('{"errors":["no survey for UPSTREAM-MARKER"]}', 404));

    const res = await POST(postRequest("{}"));

    expect(await res.json()).toEqual({ errors: ["survey not found"] });
  });

  it("never leaks upstream 404 text to the client", async () => {
    stubFetch(jsonResponse('{"errors":["no survey for UPSTREAM-MARKER"]}', 404));

    const res = await POST(postRequest("{}"));

    expect(await res.text()).not.toContain("UPSTREAM-MARKER");
  });

  it("replaces the upstream 422 body with the fixed envelope", async () => {
    stubFetch(jsonResponse('{"errors":["bad UPSTREAM-MARKER"]}', 422));

    const res = await POST(postRequest("{}"));

    expect(await res.json()).toEqual({ errors: ["The survey token was not accepted."] });
  });

  it("never leaks upstream 422 text to the client", async () => {
    stubFetch(jsonResponse('{"errors":["bad UPSTREAM-MARKER"]}', 422));

    const res = await POST(postRequest("{}"));

    expect(await res.text()).not.toContain("UPSTREAM-MARKER");
  });

  it("cancels the discarded upstream 404 body", async () => {
    const onCancel = vi.fn();
    const body = new ReadableStream<Uint8Array>({ pull() {}, cancel: onCancel });
    stubFetch(new Response(body, { status: 404 }));

    await POST(postRequest("{}"));

    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("passes a 422 status through", async () => {
    stubFetch(jsonResponse('{"errors":["bad token"]}', 422));

    const res = await POST(postRequest("{}"));

    expect(res.status).toBe(422);
  });

  it.each([429, 500, 401])("returns 502 for upstream status %i", async (status) => {
    stubFetch(jsonResponse('{"detail":"x"}', status));

    const res = await POST(postRequest("{}"));

    expect(res.status).toBe(502);
  });

  it("sets no-store on passthrough responses", async () => {
    stubFetch(jsonResponse("{}", 200));

    const res = await POST(postRequest("{}"));

    expect(res.headers.get("cache-control")).toBe("no-store");
  });

  it("sets nosniff on passthrough responses", async () => {
    stubFetch(jsonResponse("{}", 200));

    const res = await POST(postRequest("{}"));

    expect(res.headers.get("x-content-type-options")).toBe("nosniff");
  });
});

describe("POST /api/recommend upstream failures", () => {
  it("returns 504 when the backend request times out", async () => {
    stubFetch(new DOMException("signal timed out", "TimeoutError"));

    const res = await POST(postRequest("{}"));

    expect(res.status).toBe(504);
  });

  it("never logs the survey token on failure", async () => {
    stubFetch(new DOMException("signal timed out", "TimeoutError"));

    await POST(postRequest(JSON.stringify({ survey_token: SECRET_TOKEN })));

    expect(JSON.stringify(vi.mocked(console.error).mock.calls)).not.toContain(SECRET_TOKEN);
  });
});
