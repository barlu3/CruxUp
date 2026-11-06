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

// Coordinates mirror backend/app/catalog/data/shoes.yaml; every quadrant is populated.
const QUADRANT = [
  quadrantShoe("0101", "La Sportiva", "Solution", "", 0.65, -0.25, "hand", true, "Q1"),
  quadrantShoe("0102", "Scarpa", "Instinct", "VS", 0.6, -0.45, "spec", false, "Q1"),
  quadrantShoe("0103", "La Sportiva", "Miura", "VS", 0.6, -0.55, "hand", false, "Q1"),
  quadrantShoe("0104", "La Sportiva", "TC Pro", "", -0.35, -0.7, "hand", true, "Q2"),
  quadrantShoe("0105", "La Sportiva", "Mythos", "", -0.55, -0.45, "hand", false, "Q2"),
  quadrantShoe("0106", "Evolv", "Defy", "", -0.7, 0.45, "hand", true, "Q3", "mens"),
  quadrantShoe("0107", "Scarpa", "Drago", "", 0.8, 0.85, "hand", true, "Q4"),
  quadrantShoe("0108", "Scarpa", "Instinct", "VSR", 0.7, 0.4, "hand", true, "Q4"),
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
  if (method === "GET" && pathname === "/quadrant") {
    return sendJson(res, 200, QUADRANT);
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

function quadrantShoe(suffix, brand, model, version, x, y, priorSource, isAnchor, quadrant, gender = "unisex") {
  return {
    id: `5f0c1a52-6a0e-4c1d-9a51-0b6d1e3a${suffix}`,
    brand,
    model,
    version,
    gender,
    x,
    y,
    prior_source: priorSource,
    is_anchor: isAnchor,
    quadrant,
  };
}

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
