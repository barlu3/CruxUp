import { createErrorResponse } from "./backend-proxy";

const JSON_CONTENT_TYPE = /^application\/json\s*(;|$)/i;

export type JsonRequestBody =
  | { ok: true; body: Uint8Array<ArrayBuffer>; contentType: string }
  | { ok: false; response: Response };

export async function readJsonRequestBody(
  request: Request,
  maxBytes: number,
): Promise<JsonRequestBody> {
  // Transport-level CSRF hardening: a cross-site HTML form cannot send application/json.
  const contentType = request.headers.get("content-type");
  if (!contentType || !JSON_CONTENT_TYPE.test(contentType)) {
    return {
      ok: false,
      response: createErrorResponse(415, "The request must be application/json."),
    };
  }

  const declaredLength = Number(request.headers.get("content-length"));
  if (declaredLength > maxBytes) return { ok: false, response: createTooLargeResponse() };

  const body = await readCappedBody(request, maxBytes);
  if (body === "too-large") return { ok: false, response: createTooLargeResponse() };
  if (body === "aborted") {
    return {
      ok: false,
      response: createErrorResponse(400, "The request body could not be read."),
    };
  }
  return { ok: true, body, contentType };
}

function createTooLargeResponse(): Response {
  return createErrorResponse(413, "The request body is too large.");
}

// The Content-Length header can lie or be absent, so count the bytes actually read.
async function readCappedBody(
  request: Request,
  maxBytes: number,
): Promise<Uint8Array<ArrayBuffer> | "too-large" | "aborted"> {
  if (!request.body) return new Uint8Array(new ArrayBuffer(0));

  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > maxBytes) {
        await reader.cancel();
        return "too-large";
      }
      chunks.push(value);
    }
  } catch {
    return "aborted";
  } finally {
    reader.releaseLock();
  }

  const body = new Uint8Array(new ArrayBuffer(total));
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return body;
}
