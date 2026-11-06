import { forwardToBackend } from "../../lib/backend-proxy";
import { readJsonRequestBody } from "../../lib/json-request-body";

// A valid body is {"survey_token": "<uuid>"}, under 100 bytes.
const MAX_BODY_BYTES = 1024;

// Upstream 404/422 bodies are replaced with fixed messages, so nothing from the backend
// is echoed back. The body carries the survey token: it is forwarded as raw bytes and never parsed or logged.
export async function POST(request: Request): Promise<Response> {
  const parsed = await readJsonRequestBody(request, MAX_BODY_BYTES);
  if (!parsed.ok) return parsed.response;

  const headers = new Headers({ "content-type": parsed.contentType });
  return forwardToBackend(
    "/recommend",
    { method: "POST", headers, body: parsed.body },
    [200, 404, 422],
    {
      404: "survey not found",
      422: "The survey token was not accepted.",
    },
  );
}
