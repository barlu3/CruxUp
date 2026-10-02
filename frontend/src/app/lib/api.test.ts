import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchShoes } from "./api";

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
