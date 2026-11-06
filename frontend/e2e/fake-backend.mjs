// Stand-in for the FastAPI backend. The Next.js route handlers call the backend
// server-side, so page.route cannot intercept them and CI runs no backend.
import { createServer } from "node:http";

const HOST = "127.0.0.1";
const PORT = 3101;

const SHOES = [
  { id: "5f0c1a52-6a0e-4c1d-9a51-0b6d1e3a0001", brand: "Scarpa", model: "Instinct", version: "VS", gender: "unisex" },
  { id: "5f0c1a52-6a0e-4c1d-9a51-0b6d1e3a0002", brand: "Scarpa", model: "Instinct", version: "VSR", gender: "unisex" },
  { id: "5f0c1a52-6a0e-4c1d-9a51-0b6d1e3a0003", brand: "Evolv", model: "Defy", version: "", gender: "mens" },
  { id: "5f0c1a52-6a0e-4c1d-9a51-0b6d1e3a0004", brand: "Evolv", model: "Defy", version: "", gender: "womens" },
  { id: "5f0c1a52-6a0e-4c1d-9a51-0b6d1e3a0005", brand: "La Sportiva", model: "Solution", version: "", gender: "mens" },
  { id: "5f0c1a52-6a0e-4c1d-9a51-0b6d1e3a0006", brand: "La Sportiva", model: "Solution", version: "Comp", gender: "mens" },
];

// A budget of exactly 1 USD is the sentinel that makes POST /survey fail with
// 422, so tests can exercise the server-error path without a real validator.
const REJECTED_BUDGET_SENTINEL = 1;

const server = createServer((req, res) => {
  const { method } = req;
  const { pathname } = new URL(req.url ?? "/", `http://${HOST}:${PORT}`);

  if (method === "GET" && pathname === "/shoes") {
    return sendJson(res, 200, SHOES);
  }
  if (method === "POST" && pathname === "/survey") {
    return readBody(req).then((raw) => {
      let body;
      try {
        body = JSON.parse(raw);
      } catch {
        return sendJson(res, 422, { errors: ["body is not valid JSON"] });
      }
      if (body?.budget_cap_usd === REJECTED_BUDGET_SENTINEL) {
        return sendJson(res, 422, { errors: ["budget_cap_usd=1 is below the minimum"] });
      }
      return sendJson(res, 201, { survey_token: "e2e-token" });
    });
  }
  return sendJson(res, 404, { errors: ["not found"] });
});

server.listen(PORT, HOST);

function sendJson(res, status, body) {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(JSON.stringify(body));
}

function readBody(req) {
  return new Promise((resolve) => {
    let data = "";
    req.on("data", (chunk) => (data += chunk));
    req.on("end", () => resolve(data));
  });
}
