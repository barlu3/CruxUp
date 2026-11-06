import { callBackend, relay } from "../_lib/backend";

const UNAVAILABLE = "The catalogue service is unavailable. Please try again later.";

export async function GET(): Promise<Response> {
  try {
    return await relay(await callBackend("/shoes", { method: "GET" }), [200], UNAVAILABLE);
  } catch {
    return Response.json({ errors: [UNAVAILABLE] }, { status: 502 });
  }
}
