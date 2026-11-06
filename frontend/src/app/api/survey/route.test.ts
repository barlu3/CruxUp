// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { POST } from "./route";

const MAX_BODY_BYTES = 32 * 1024;
const UNAVAILABLE = { errors: ["The service is temporarily unavailable."] };

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
  return new Request("http://localhost:3000/api/survey", {
    method: "POST",
    body,
    headers: { "content-type": "application/json", ...headers },
  });
}

function streamingRequest(body: ReadableStream<Uint8Array>) {
  return new Request("http://localhost:3000/api/survey", {
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

beforeEach(() => {
  vi.stubEnv("CRUXUP_API_URL", "http://backend.test:9000");
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe("POST /api/survey forwarding", () => {
  it("forwards the body byte-for-byte", async () => {
    const fetchMock = stubFetch(jsonResponse("{}", 201));
    const bytes = new Uint8Array([0x7b, 0xff, 0x00, 0xc3, 0x28, 0x7d]);

    await POST(postRequest(bytes));

    expect(new Uint8Array(fetchMock.mock.calls[0][1]!.body as ArrayBuffer)).toEqual(bytes);
  });

  it("sends the request to CRUXUP_API_URL/survey", async () => {
    const fetchMock = stubFetch(jsonResponse("{}", 201));

    await POST(postRequest("{}"));

    expect(fetchMock.mock.calls[0][0]).toBe("http://backend.test:9000/survey");
  });

  it("uses POST towards the backend", async () => {
    const fetchMock = stubFetch(jsonResponse("{}", 201));

    await POST(postRequest("{}"));

    expect(fetchMock.mock.calls[0][1]?.method).toBe("POST");
  });

  it("uses the default backend URL when CRUXUP_API_URL is unset", async () => {
    delete process.env.CRUXUP_API_URL;
    const fetchMock = stubFetch(jsonResponse("{}", 201));

    await POST(postRequest("{}"));

    expect(fetchMock.mock.calls[0][0]).toBe("http://127.0.0.1:8000/survey");
  });

  it("forwards only the content-type header", async () => {
    const fetchMock = stubFetch(jsonResponse("{}", 201));

    await POST(
      postRequest("{}", { cookie: "session=secret", authorization: "Bearer x" }),
    );

    expect(Object.fromEntries(new Headers(fetchMock.mock.calls[0][1]!.headers))).toEqual({
      "content-type": "application/json",
    });
  });

  it("attaches an abort signal to the upstream request", async () => {
    const fetchMock = stubFetch(jsonResponse("{}", 201));

    await POST(postRequest("{}"));

    expect(fetchMock.mock.calls[0][1]?.signal).toBeInstanceOf(AbortSignal);
  });

  it("refuses to follow upstream redirects", async () => {
    const fetchMock = stubFetch(jsonResponse("{}", 201));

    await POST(postRequest("{}"));

    expect(fetchMock.mock.calls[0][1]?.redirect).toBe("error");
  });
});

describe("POST /api/survey content type", () => {
  it("returns 415 for a non-JSON content type", async () => {
    stubFetch(jsonResponse("{}", 201));

    const res = await POST(postRequest("a=b", { "content-type": "text/plain" }));

    expect(res.status).toBe(415);
  });

  it("returns the fixed envelope for a non-JSON content type", async () => {
    stubFetch(jsonResponse("{}", 201));

    const res = await POST(postRequest("a=b", { "content-type": "text/plain" }));

    expect(await res.json()).toEqual({
      errors: ["The request must be application/json."],
    });
  });

  it("does not call fetch for a non-JSON content type", async () => {
    const fetchMock = stubFetch(jsonResponse("{}", 201));

    await POST(postRequest("a=b", { "content-type": "application/x-www-form-urlencoded" }));

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("returns 415 when the content type is missing", async () => {
    stubFetch(jsonResponse("{}", 201));
    const req = new Request("http://localhost:3000/api/survey", {
      method: "POST",
      body: new Uint8Array([1]),
    });

    const res = await POST(req);

    expect(res.status).toBe(415);
  });

  it("accepts application/json with a charset parameter", async () => {
    stubFetch(jsonResponse("{}", 201));

    const res = await POST(
      postRequest("{}", { "content-type": "application/json; charset=utf-8" }),
    );

    expect(res.status).toBe(201);
  });
});

describe("POST /api/survey body cap", () => {
  it("returns 413 when Content-Length exceeds the cap", async () => {
    stubFetch(jsonResponse("{}", 201));

    const res = await POST(
      postRequest("{}", { "content-length": String(MAX_BODY_BYTES + 1) }),
    );

    expect(res.status).toBe(413);
  });

  it("does not call fetch when Content-Length exceeds the cap", async () => {
    const fetchMock = stubFetch(jsonResponse("{}", 201));

    await POST(postRequest("{}", { "content-length": String(MAX_BODY_BYTES + 1) }));

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("returns 413 for an oversize streamed body without Content-Length", async () => {
    stubFetch(jsonResponse("{}", 201));
    const chunk = new Uint8Array(MAX_BODY_BYTES / 2 + 1);

    const res = await POST(streamingRequest(streamOf([chunk, chunk])));

    expect(res.status).toBe(413);
  });

  it("does not call fetch for an oversize streamed body", async () => {
    const fetchMock = stubFetch(jsonResponse("{}", 201));
    const chunk = new Uint8Array(MAX_BODY_BYTES / 2 + 1);

    await POST(streamingRequest(streamOf([chunk, chunk])));

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("returns 413 when the real body is larger than a lying Content-Length", async () => {
    stubFetch(jsonResponse("{}", 201));

    const res = await POST(
      postRequest("x".repeat(MAX_BODY_BYTES + 1), { "content-length": "2" }),
    );

    expect(res.status).toBe(413);
  });

  it("accepts a body of exactly the cap", async () => {
    stubFetch(jsonResponse("{}", 201));

    const res = await POST(postRequest("x".repeat(MAX_BODY_BYTES)));

    expect(res.status).toBe(201);
  });

  it("returns 400 when the client aborts mid-body", async () => {
    stubFetch(jsonResponse("{}", 201));
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.error(new Error("client aborted"));
      },
    });

    const res = await POST(streamingRequest(body));

    expect(res.status).toBe(400);
  });

  it("does not call fetch when the client aborts mid-body", async () => {
    const fetchMock = stubFetch(jsonResponse("{}", 201));
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.error(new Error("client aborted"));
      },
    });

    await POST(streamingRequest(body));

    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("POST /api/survey upstream responses", () => {
  it("passes a 201 status through", async () => {
    stubFetch(jsonResponse('{"survey_token":"abc-123"}', 201));

    const res = await POST(postRequest("{}"));

    expect(res.status).toBe(201);
  });

  it("passes a 201 body through unchanged", async () => {
    const body = '{"survey_token":"abc-123"}';
    stubFetch(jsonResponse(body, 201));

    const res = await POST(postRequest("{}"));

    expect(await res.text()).toBe(body);
  });

  it("passes a 422 status through", async () => {
    stubFetch(jsonResponse('{"errors":["q1 is required"]}', 422));

    const res = await POST(postRequest("{}"));

    expect(res.status).toBe(422);
  });

  it("passes a 422 body through unchanged", async () => {
    const body = '{"errors":["q1 is required"]}';
    stubFetch(jsonResponse(body, 422));

    const res = await POST(postRequest("{}"));

    expect(await res.text()).toBe(body);
  });

  it("sets content-type to application/json instead of reflecting upstream", async () => {
    stubFetch(
      new Response("{}", { status: 201, headers: { "content-type": "text/html" } }),
    );

    const res = await POST(postRequest("{}"));

    expect(res.headers.get("content-type")).toBe("application/json");
  });

  it("sets nosniff on passthrough responses", async () => {
    stubFetch(jsonResponse("{}", 201));

    const res = await POST(postRequest("{}"));

    expect(res.headers.get("x-content-type-options")).toBe("nosniff");
  });

  it("sets no-store on passthrough responses", async () => {
    stubFetch(jsonResponse("{}", 201));

    const res = await POST(postRequest("{}"));

    expect(res.headers.get("cache-control")).toBe("no-store");
  });

  it("sets nosniff on proxy error responses", async () => {
    stubFetch(jsonResponse("{}", 500));

    const res = await POST(postRequest("{}"));

    expect(res.headers.get("x-content-type-options")).toBe("nosniff");
  });

  it("sets no-store on proxy error responses", async () => {
    stubFetch(jsonResponse("{}", 500));

    const res = await POST(postRequest("{}"));

    expect(res.headers.get("cache-control")).toBe("no-store");
  });

  it.each([200, 404, 429, 500, 502])(
    "returns 502 for upstream status %i",
    async (status) => {
      stubFetch(jsonResponse('{"detail":"x"}', status));

      const res = await POST(postRequest("{}"));

      expect(res.status).toBe(502);
    },
  );

  it.each([301, 401])("returns 502 for upstream status %i", async (status) => {
    stubFetch(new Response(null, { status }));

    const res = await POST(postRequest("{}"));

    expect(res.status).toBe(502);
  });

  it("never leaks the upstream 500 body to the client", async () => {
    stubFetch(jsonResponse('{"detail":"Traceback secret"}', 500));

    const res = await POST(postRequest("{}"));

    expect(await res.json()).toEqual({
      errors: ["The service returned an unexpected response."],
    });
  });

  it("returns 503 for an upstream 503", async () => {
    stubFetch(jsonResponse('{"detail":"db down"}', 503));

    const res = await POST(postRequest("{}"));

    expect(res.status).toBe(503);
  });

  it("returns the fixed envelope for an upstream 503", async () => {
    stubFetch(jsonResponse('{"detail":"db down"}', 503));

    const res = await POST(postRequest("{}"));

    expect(await res.json()).toEqual(UNAVAILABLE);
  });

  it("cancels the discarded upstream body", async () => {
    const onCancel = vi.fn();
    const body = new ReadableStream<Uint8Array>({
      pull() {},
      cancel: onCancel,
    });
    stubFetch(new Response(body, { status: 500 }));

    await POST(postRequest("{}"));

    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});

describe("POST /api/survey upstream failures", () => {
  const refused = () =>
    new TypeError("fetch failed", {
      cause: Object.assign(new Error("connect ECONNREFUSED"), {
        code: "ECONNREFUSED",
      }),
    });

  it("returns 503 when the backend refuses the connection", async () => {
    stubFetch(refused());

    const res = await POST(postRequest("{}"));

    expect(res.status).toBe(503);
  });

  it("returns the fixed envelope when the connection is refused", async () => {
    stubFetch(refused());

    const res = await POST(postRequest("{}"));

    expect(await res.json()).toEqual(UNAVAILABLE);
  });

  it("returns 503 when fetch rejects because of a redirect", async () => {
    stubFetch(new TypeError("fetch failed"));

    const res = await POST(postRequest("{}"));

    expect(res.status).toBe(503);
  });

  it("returns 504 when the backend request times out", async () => {
    stubFetch(new DOMException("signal timed out", "TimeoutError"));

    const res = await POST(postRequest("{}"));

    expect(res.status).toBe(504);
  });

  it("returns the fixed envelope on timeout", async () => {
    stubFetch(new DOMException("signal timed out", "TimeoutError"));

    const res = await POST(postRequest("{}"));

    expect(await res.json()).toEqual({
      errors: ["The service took too long to respond."],
    });
  });

  it("logs the error name and message on failure", async () => {
    stubFetch(new DOMException("signal timed out", "TimeoutError"));

    await POST(postRequest("{}"));

    expect(console.error).toHaveBeenCalledWith(
      expect.stringContaining("TimeoutError: signal timed out"),
    );
  });

  it("never logs the backend URL", async () => {
    stubFetch(new TypeError("fetch failed"));

    await POST(postRequest("{}"));

    expect(JSON.stringify(vi.mocked(console.error).mock.calls)).not.toContain("backend.test");
  });
});
