import { callBackend, isJsonContentType, readCapped, relay } from "../_lib/backend";

// A valid body is {"survey_token": "<uuid>"}, under 100 bytes.
const MAX_RECOMMEND_BODY_BYTES = 1024;
const UNAVAILABLE = "The results service is unavailable. Please try again later.";
// Fixed bodies, so nothing the backend says about a token is echoed back.
const FIXED_ERRORS: Record<number, string> = {
  404: "survey not found",
  422: "The survey token was not accepted.",
};

// The body carries the survey token: forwarded as raw bytes, never parsed or logged.
export async function POST(request: Request): Promise<Response> {
  if (!isJsonContentType(request.headers.get("content-type"))) {
    return Response.json(
      { errors: ["request body must be JSON (content-type: application/json)"] },
      { status: 415 },
    );
  }
  try {
    const body = await readCapped(request, MAX_RECOMMEND_BODY_BYTES);
    if (body === null) {
      return Response.json(
        { errors: [`request body exceeds ${MAX_RECOMMEND_BODY_BYTES} bytes`] },
        { status: 413 },
      );
    }
    const upstream = await callBackend("/recommend", { method: "POST", body });
    const fixed = FIXED_ERRORS[upstream.status];
    if (fixed !== undefined) {
      await upstream.body?.cancel();
      return Response.json({ errors: [fixed] }, { status: upstream.status });
    }
    return await relay(upstream, [200], UNAVAILABLE);
  } catch {
    return Response.json({ errors: [UNAVAILABLE] }, { status: 502 });
  }
}
