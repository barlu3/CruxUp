import { createErrorResponse, forwardToBackend } from "../../lib/backend-proxy";

const MAX_BODY_BYTES = 32 * 1024;
const JSON_CONTENT_TYPE = /^application\/json\s*(;|$)/i;

export async function POST(request: Request): Promise<Response> {
  // Transport-level CSRF hardening: a cross-site HTML form cannot send application/json.
  const contentType = request.headers.get("content-type");
  if (!contentType || !JSON_CONTENT_TYPE.test(contentType)) {
    return createErrorResponse(415, "The request must be application/json.");
  }

  const declaredLength = Number(request.headers.get("content-length"));
  if (declaredLength > MAX_BODY_BYTES) return createTooLargeResponse();

  const body = await readCappedBody(request);
  if (body === "too-large") return createTooLargeResponse();
  if (body === "aborted") {
    return createErrorResponse(400, "The request body could not be read.");
  }

  // Only content-type is forwarded: cookies and auth headers stay out of the backend.
  const headers = new Headers({ "content-type": contentType });
  return forwardToBackend("/survey", { method: "POST", headers, body }, [201, 422]);
}

function createTooLargeResponse(): Response {
  return createErrorResponse(413, "The request body is too large.");
}

// The Content-Length header can lie or be absent, so count the bytes actually read.
async function readCappedBody(
  request: Request,
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
      if (total > MAX_BODY_BYTES) {
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
