import { forwardToBackend } from "../../lib/backend-proxy";

export const dynamic = "force-dynamic";

export async function GET(): Promise<Response> {
  return forwardToBackend("/quadrant", { method: "GET" }, [200]);
}
