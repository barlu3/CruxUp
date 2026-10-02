import {
  MAX_SURVEY_BODY_BYTES,
  callBackend,
  isJsonContentType,
  readCapped,
  relay,
} from "../_lib/backend";

// No parsing or validation here: the FastAPI layer owns every rule.
export async function POST(request: Request): Promise<Response> {
  if (!isJsonContentType(request.headers.get("content-type"))) {
    return Response.json(
      { errors: ["request body must be JSON (content-type: application/json)"] },
      { status: 415 },
    );
  }
  try {
    const body = await readCapped(request, MAX_SURVEY_BODY_BYTES);
    if (body === null) {
      return Response.json(
        { errors: [`request body exceeds ${MAX_SURVEY_BODY_BYTES} bytes`] },
        { status: 413 },
      );
    }
    return await relay(await callBackend("/survey", { method: "POST", body }));
  } catch {
    return Response.json(
      { errors: ["The survey service is unavailable. Please try again later."] },
      { status: 502 },
    );
  }
}
