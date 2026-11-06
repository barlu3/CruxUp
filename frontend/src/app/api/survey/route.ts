import { forwardToBackend } from "../../lib/backend-proxy";
import { readJsonRequestBody } from "../../lib/json-request-body";

const MAX_BODY_BYTES = 32 * 1024;

export async function POST(request: Request): Promise<Response> {
  const parsed = await readJsonRequestBody(request, MAX_BODY_BYTES);
  if (!parsed.ok) return parsed.response;

  // Only content-type is forwarded: cookies and auth headers stay out of the backend.
  const headers = new Headers({ "content-type": parsed.contentType });
  return forwardToBackend(
    "/survey",
    { method: "POST", headers, body: parsed.body },
    [201, 422],
  );
}
