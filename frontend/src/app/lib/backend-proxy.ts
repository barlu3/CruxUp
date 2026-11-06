// Server-only: the backend origin must never reach the browser, so this module
// is imported by route handlers alone and the env var has no NEXT_PUBLIC_ prefix.

const DEFAULT_API_URL = "http://127.0.0.1:8000";
const BACKEND_TIMEOUT_MS = 10_000;

const SECURITY_HEADERS = {
  "content-type": "application/json",
  "x-content-type-options": "nosniff",
  "cache-control": "no-store",
} as const;

type BackendPath = "/survey" | "/shoes" | "/quadrant" | "/recommend";

export function createErrorResponse(status: number, message: string): Response {
  return Response.json({ errors: [message] }, { status, headers: SECURITY_HEADERS });
}

// No retry: the POST endpoints (/survey, /recommend) are not safe to repeat blindly.
// Statuses outside `passthroughStatuses` become 502 so the backend cannot surface
// redirects, auth or rate-limit responses. A status listed in `fixedMessages` keeps its
// code but its body is replaced, so a route can refuse to echo backend text.
export async function forwardToBackend(
  path: BackendPath,
  init: RequestInit,
  passthroughStatuses: readonly number[],
  fixedMessages: Readonly<Record<number, string>> = {},
): Promise<Response> {
  const baseUrl = process.env.CRUXUP_API_URL || DEFAULT_API_URL;

  let upstream: Response;
  try {
    upstream = await fetch(`${baseUrl}${path}`, {
      ...init,
      redirect: "error",
      signal: AbortSignal.timeout(BACKEND_TIMEOUT_MS),
    });
  } catch (error) {
    // The URL is deliberately left out of the log line.
    const reason =
      error instanceof Error ? `${error.name}: ${error.message}` : "unknown error";
    console.error(`Backend request to ${path} failed: ${reason}`);
    if (error instanceof Error && error.name === "TimeoutError") {
      return createErrorResponse(504, "The service took too long to respond.");
    }
    return createErrorResponse(503, "The service is temporarily unavailable.");
  }

  const fixedMessage = fixedMessages[upstream.status];
  if (fixedMessage !== undefined && passthroughStatuses.includes(upstream.status)) {
    await upstream.body?.cancel();
    return createErrorResponse(upstream.status, fixedMessage);
  }

  if (passthroughStatuses.includes(upstream.status)) {
    return new Response(upstream.body, {
      status: upstream.status,
      headers: SECURITY_HEADERS,
    });
  }

  await upstream.body?.cancel();
  if (upstream.status === 503) {
    return createErrorResponse(503, "The service is temporarily unavailable.");
  }
  return createErrorResponse(502, "The service returned an unexpected response.");
}
