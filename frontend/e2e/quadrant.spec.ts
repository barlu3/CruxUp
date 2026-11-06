import { expect, test } from "@playwright/test";
import type { Locator, Page } from "@playwright/test";

// Fake-backend fixture order by x: Defy, Mythos, TC Pro, ...
const FIRST_SHOE = /^Evolv Defy/;
const SECOND_SHOE = "La Sportiva Mythos (unisex)";

test("home link to the quadrant lands on the quadrant page", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Explore the shoe quadrant" }).click();
  await expect(page).toHaveURL(/\/quadrant$/);
});

test("quadrant page shows the Q4 quadrant label on the chart", async ({ page }) => {
  await openQuadrant(page);
  await expect(page.locator("figure svg text", { hasText: "Q4" })).toBeVisible();
});

test("table lists Scarpa Drago in the Q4 group", async ({ page }) => {
  await openQuadrant(page);
  const q4Group = page.locator("tbody").filter({ hasText: "Q4 · Performance + soft" });
  await expect(q4Group).toContainText("Scarpa Drago");
});

test("Tab then ArrowRight shows a tooltip naming the second shoe by x-order", async ({ page }) => {
  await openQuadrant(page);
  await page.keyboard.press("Tab");
  await page.keyboard.press("ArrowRight");
  await expect(tooltip(page)).toContainText(SECOND_SHOE);
});

test("hovering the Drago point shows its tooltip", async ({ page }) => {
  await openQuadrant(page);
  await dragoMark(page).hover();
  await expect(tooltip(page)).toContainText("Scarpa Drago (unisex)");
});

test("Escape hides a shown tooltip", async ({ page }) => {
  await openQuadrant(page);
  await dragoMark(page).hover();
  await expect(tooltip(page)).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(tooltip(page)).toBeHidden();
});

test("quadrant page has no horizontal page scroll at 375px", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await openQuadrant(page);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

async function openQuadrant(page: Page) {
  await page.goto("/quadrant");
  await expect(page.getByRole("img", { name: FIRST_SHOE })).toBeVisible();
}

// The tooltip is aria-hidden by design, so role queries would skip it.
function tooltip(page: Page): Locator {
  return page.locator('[role="tooltip"]');
}

// The mark is the topmost circle, so hovering it passes Playwright's hit-target check; the
// group's own box is skewed by its text label.
function dragoMark(page: Page): Locator {
  return page.getByRole("img", { name: /^Scarpa Drago/ }).locator("circle").last();
}
