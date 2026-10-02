// Server-only helpers shared by the two route handlers. The FastAPI base URL
// comes from CRUXUP_API_URL, read per request (never NEXT_PUBLIC_).

export const MAX_SURVEY_BODY_BYTES = 65_536;
const DEFAULT_API_URL = "http://127.0.0.1:8000";
const UPSTREAM_TIMEOUT_MS = 10_000;

export function backendUrl(path: string): string {
  const base = (process.env.CRUXUP_API_URL || DEFAULT_API_URL).replace(/\/+$/, "");
  return `${base}${path}`;
}

/** Relay the upstream status and JSON body verbatim. */
export async function relay(upstream: Response): Promise<Response> {
  const text = await upstream.text();
  return new Response(text, {
    status: upstream.status,
    headers: { "content-type": "application/json" },
  });
}

/** A fresh upstream request: fixed headers only, never the caller's. */
export function callBackend(
  path: string,
  init: { method: "GET" } | { method: "POST"; body: Uint8Array<ArrayBuffer> },
): Promise<Response> {
  const headers: Record<string, string> = { accept: "application/json" };
  if (init.method === "POST") headers["content-type"] = "application/json";
  return fetch(backendUrl(path), {
    ...init,
    headers,
    cache: "no-store",
    redirect: "error", // the backend never redirects; never follow one
    signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
  });
}

/**
 * Read a request body with a running byte count, stopping as soon as it passes
 * the cap. Returns null when the body is too large.
 */
export async function readCapped(
  request: Request,
  cap: number,
): Promise<Uint8Array<ArrayBuffer> | null> {
  const declared = Number(request.headers.get("content-length"));
  if (Number.isFinite(declared) && declared > cap) return null;
  const chunks: Uint8Array[] = [];
  let total = 0;
  if (request.body) {
    const reader = request.body.getReader();
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > cap) {
        await reader.cancel();
        return null;
      }
      chunks.push(value);
    }
  }
  const out = new Uint8Array(new ArrayBuffer(total));
  let offset = 0;
  for (const c of chunks) {
    out.set(c, offset);
    offset += c.byteLength;
  }
  return out;
}

/**
 * `application/json` or `application/*+json`, case-insensitive, parameters
 * ignored. Mirrors the backend's _is_json_content_type: a non-JSON type would
 * reach FastAPI as raw bytes and be rejected there.
 */
export function isJsonContentType(header: string | null): boolean {
  if (!header) return false;
  const type = header.split(";")[0].trim().toLowerCase();
  return type === "application/json" || (type.startsWith("application/") && type.endsWith("+json"));
}
