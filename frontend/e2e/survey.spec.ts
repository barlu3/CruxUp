import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const MOCK = "http://127.0.0.1:8100";
const APP_ORIGIN = "http://localhost:3100";

// Every browser request must stay on the app's own origin (data:/blob: aside),
// which also proves the backend (8100 here, 8000 by default) is never called.
function foreignRequests(urls: string[]): string[] {
  return urls.filter((u) => {
    if (u.startsWith("data:") || u.startsWith("blob:")) return false;
    return new URL(u).origin !== APP_ORIGIN;
  });
}

async function axeViolations(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  return results.violations;
}
const anchorsOnly = {
  known_good_shoes: [
    { brand: "Scarpa", model: "Instinct", version: "VSR", gender: "unisex" },
  ],
};

test("keyboard only: pick an anchor and submit with nothing else", async ({ page, request }) => {
  const browserRequests: string[] = [];
  page.on("request", (r) => browserRequests.push(r.url()));

  await page.goto("/survey");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  const picker = page.getByRole("combobox", { name: "Shoes that fit you well" });
  await expect(picker).toBeEnabled();
  await picker.focus();
  await page.keyboard.type("instinct");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("option", { name: "Scarpa Instinct VSR (unisex)" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await page.keyboard.press("Enter");
  await page.keyboard.press("Tab"); // size
  await page.keyboard.press("Tab"); // remove
  await page.keyboard.press("Tab"); // bad picker
  await page.keyboard.press("Tab"); // submit
  await expect(page.getByRole("button", { name: "Submit answers" })).toBeFocused();
  await page.keyboard.press("Enter");

  await expect(page.getByRole("status").filter({ hasText: "Thank you" })).toContainText("Thank you");
  const last = await request.get(`${MOCK}/__last-survey`);
  expect(await last.json()).toEqual(anchorsOnly);
  expect(foreignRequests(browserRequests)).toEqual([]);
});

async function pickDrago(page: Page) {
  await page.goto("/survey");
  const picker = page.getByRole("combobox", { name: "Shoes that fit you well" });
  await expect(picker).toBeEnabled();
  await picker.focus();
  await page.keyboard.type("drago");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");
}

test("a size error is explained in plain language and links to its field", async ({ page }) => {
  await pickDrago(page);
  const size = page.getByLabel("Size (optional) for Scarpa Drago (unisex)");
  await size.fill("4,1");
  await page.getByRole("button", { name: "Submit answers" }).click();
  const alert = page.locator("form [role=alert]");
  await expect(alert).toBeFocused();
  await expect(alert).toContainText("Size for Scarpa Drago (unisex): use only letters");
  await expect(alert).not.toContainText("known_");
  await expect(alert).not.toContainText("D4");
  await expect(size).toHaveAttribute("aria-invalid", "true");
  await alert.getByRole("link").click();
  await expect(size).toBeFocused();
  await expect(size).toHaveValue("4,1");
});

test("an unrecognised 422 message stays plain text inside Technical details", async ({ page }) => {
  await pickDrago(page);
  await page.getByLabel("Size (optional) for Scarpa Drago (unisex)").fill("__e2e_422__");
  await page.getByRole("button", { name: "Submit answers" }).click();
  const alert = page.locator("form [role=alert]");
  await expect(alert).toContainText("One of your answers could not be accepted");
  await expect(alert.locator("details")).toContainText("<b>rejected</b>");
  await expect(alert.locator("b")).toHaveCount(0);
});

test("the browser never calls the backend directly", async ({ page }) => {
  const urls: string[] = [];
  page.on("request", (r) => urls.push(r.url()));
  await page.goto("/survey");
  await expect(page.getByRole("combobox", { name: "Shoes that fit you well" })).toBeEnabled();
  await page.getByRole("button", { name: "Submit answers" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Thank you" })).toBeVisible();
  expect(urls.some((u) => u.endsWith("/api/shoes"))).toBe(true);
  expect(urls.some((u) => u.endsWith("/api/survey"))).toBe(true);
  expect(foreignRequests(urls)).toEqual([]);
});

test.describe("WCAG 2 A/AA scans", () => {
  const picker = (page: Page) =>
    page.getByRole("combobox", { name: "Shoes that fit you well" });

  test("initial questionnaire", async ({ page }) => {
    await page.goto("/survey");
    await expect(picker(page)).toBeEnabled();
    expect(await axeViolations(page)).toEqual([]);
  });

  test("with the suggestion list open", async ({ page }) => {
    await page.goto("/survey");
    await expect(picker(page)).toBeEnabled();
    await picker(page).focus();
    await page.keyboard.type("instinct");
    await page.keyboard.press("ArrowDown");
    await expect(page.getByRole("listbox")).toBeVisible();
    expect(await axeViolations(page)).toEqual([]);
  });

  test("with a shoe selected (size input and remove button)", async ({ page }) => {
    await page.goto("/survey");
    await expect(picker(page)).toBeEnabled();
    await picker(page).focus();
    await page.keyboard.type("drago");
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("Enter");
    await expect(page.getByRole("button", { name: "Remove Scarpa Drago (unisex)" })).toBeVisible();
    expect(await axeViolations(page)).toEqual([]);
  });

  test("with the 422 alert shown", async ({ page }) => {
    await page.goto("/survey");
    await expect(picker(page)).toBeEnabled();
    await picker(page).focus();
    await page.keyboard.type("drago");
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("Enter");
    await page.getByLabel("Size (optional) for Scarpa Drago (unisex)").fill("4,1");
    await page.getByRole("button", { name: "Submit answers" }).click();
    await expect(page.locator("form [role=alert]")).toBeFocused();
    expect(await axeViolations(page)).toEqual([]);
  });

  test("with the unrecognised-error details open", async ({ page }) => {
    await pickDrago(page);
    await page.getByLabel("Size (optional) for Scarpa Drago (unisex)").fill("__e2e_422__");
    await page.getByRole("button", { name: "Submit answers" }).click();
    await page.locator("form [role=alert] summary").click();
    expect(await axeViolations(page)).toEqual([]);
  });

  test("on the confirmation", async ({ page }) => {
    await page.goto("/survey");
    await expect(picker(page)).toBeEnabled();
    await page.getByRole("button", { name: "Submit answers" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Thank you" })).toContainText("Thank you");
    expect(await axeViolations(page)).toEqual([]);
  });
});

test("no backend documentation or extra methods are exposed", async ({ request }) => {
  for (const path of ["/api/docs", "/api/openapi.json", "/api/redoc"]) {
    expect((await request.get(path)).status(), path).toBe(404);
  }
  expect((await request.get("/api/survey")).status()).not.toBe(200);
});
