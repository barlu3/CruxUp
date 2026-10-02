// Dependency-free stand-in for the FastAPI backend, used only by the e2e run.
// GET /shoes serves the real-catalogue fixture; POST /survey records the last
// body. A body containing "__e2e_422__" is answered with a 422.
import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const PORT = 8100;
const here = dirname(fileURLToPath(import.meta.url));
const shoes = readFileSync(join(here, "fixtures", "shoes.json"), "utf8");
let lastSurvey = null;

function send(res, status, body) {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(typeof body === "string" ? body : JSON.stringify(body));
}

createServer((req, res) => {
  const { pathname } = new URL(req.url ?? "/", `http://127.0.0.1:${PORT}`);
  if (req.method === "GET" && pathname === "/shoes") return send(res, 200, shoes);
  if (req.method === "GET" && pathname === "/__last-survey") return send(res, 200, lastSurvey);
  if (req.method === "POST" && pathname === "/survey") {
    const chunks = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => {
      const raw = Buffer.concat(chunks).toString("utf8");
      try {
        lastSurvey = JSON.parse(raw);
      } catch {
        return send(res, 422, { errors: ["request body is not valid JSON"] });
      }
      // Size with a comma: the exact charset message the real backend sends
      // (anchors.py), indexed by position in its list.
      const sizeErrors = [];
      for (const key of ["known_good_shoes", "known_bad_shoes"]) {
        const list = Array.isArray(lastSurvey?.[key]) ? lastSurvey[key] : [];
        list.forEach((entry, i) => {
          if (typeof entry?.size === "string" && entry.size.includes(",")) {
            sizeErrors.push(
              `${key}[${i}]: 'size' contains [','] -- it records a brand size, not free text (D4: no direct identifiers)`,
            );
          }
        });
      }
      if (sizeErrors.length > 0) return send(res, 422, { errors: sizeErrors });
      if (raw.includes("__e2e_422__")) {
        return send(res, 422, { errors: ["size: e2e marker <b>rejected</b>"] });
      }
      return send(res, 201, { survey_token: "e2e-token" });
    });
    return;
  }
  send(res, 404, { detail: "Not Found" });
}).listen(PORT, "127.0.0.1", () => console.log(`mock api on ${PORT}`));
