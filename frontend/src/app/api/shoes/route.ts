import { callBackend, relay } from "../_lib/backend";

export async function GET(): Promise<Response> {
  try {
    return await relay(await callBackend("/shoes", { method: "GET" }));
  } catch {
    return Response.json({ detail: "catalogue service unavailable" }, { status: 502 });
  }
}
