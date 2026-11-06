// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GET, dynamic } from "./route";

function stubFetch(response: Response | Error) {
  const fetchMock = vi.fn<typeof fetch>(async () => {
    if (response instanceof Error) throw response;
    return response;
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
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

describe("GET /api/shoes", () => {
  it("is never prerendered", () => {
    expect(dynamic).toBe("force-dynamic");
  });

  it("requests CRUXUP_API_URL/shoes", async () => {
    const fetchMock = stubFetch(Response.json([]));

    await GET();

    expect(fetchMock.mock.calls[0][0]).toBe("http://backend.test:9000/shoes");
  });

  it("uses GET towards the backend", async () => {
    const fetchMock = stubFetch(Response.json([]));

    await GET();

    expect(fetchMock.mock.calls[0][1]?.method).toBe("GET");
  });

  it("uses the default backend URL when CRUXUP_API_URL is unset", async () => {
    delete process.env.CRUXUP_API_URL;
    const fetchMock = stubFetch(Response.json([]));

    await GET();

    expect(fetchMock.mock.calls[0][0]).toBe("http://127.0.0.1:8000/shoes");
  });

  it("never lets a client cookie reach the backend", async () => {
    const fetchMock = stubFetch(Response.json([]));
    const handler: (request: Request) => Promise<Response> = GET;

    await handler(
      new Request("http://localhost:3000/api/shoes", {
        headers: { cookie: "session=secret" },
      }),
    );

    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).get("cookie")).toBeNull();
  });

  it("attaches an abort signal to the upstream request", async () => {
    const fetchMock = stubFetch(Response.json([]));

    await GET();

    expect(fetchMock.mock.calls[0][1]?.signal).toBeInstanceOf(AbortSignal);
  });

  it("refuses to follow upstream redirects", async () => {
    const fetchMock = stubFetch(Response.json([]));

    await GET();

    expect(fetchMock.mock.calls[0][1]?.redirect).toBe("error");
  });

  it("passes the shoe list through unchanged", async () => {
    const body = '[{"id":1,"name":"Solution"}]';
    stubFetch(new Response(body, { status: 200 }));

    const res = await GET();

    expect(await res.text()).toBe(body);
  });

  it("sets content-type to application/json", async () => {
    stubFetch(new Response("[]", { status: 200, headers: { "content-type": "text/html" } }));

    const res = await GET();

    expect(res.headers.get("content-type")).toBe("application/json");
  });

  it("sets nosniff on the shoe list", async () => {
    stubFetch(new Response("[]", { status: 200, headers: { "content-type": "text/html" } }));

    const res = await GET();

    expect(res.headers.get("x-content-type-options")).toBe("nosniff");
  });

  it("sets no-store on the shoe list", async () => {
    stubFetch(new Response("[]", { status: 200, headers: { "content-type": "text/html" } }));

    const res = await GET();

    expect(res.headers.get("cache-control")).toBe("no-store");
  });

  it("returns 502 for an upstream 201", async () => {
    stubFetch(new Response("[]", { status: 201 }));

    const res = await GET();

    expect(res.status).toBe(502);
  });

  it("returns 502 for an upstream 404", async () => {
    stubFetch(new Response("nope", { status: 404 }));

    const res = await GET();

    expect(res.status).toBe(502);
  });

  it("does not leak the upstream 500 body", async () => {
    stubFetch(new Response("Traceback secret", { status: 500 }));

    const res = await GET();

    expect(await res.json()).toEqual({
      errors: ["The service returned an unexpected response."],
    });
  });

  it("returns 503 when the backend refuses the connection", async () => {
    stubFetch(new TypeError("fetch failed"));

    const res = await GET();

    expect(res.status).toBe(503);
  });

  it("returns 504 when the backend request times out", async () => {
    stubFetch(new DOMException("signal timed out", "TimeoutError"));

    const res = await GET();

    expect(res.status).toBe(504);
  });
});
