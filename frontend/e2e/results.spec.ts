import { expect, test } from "@playwright/test";
import type { Locator, Page } from "@playwright/test";

// Must match SURVEY_TOKEN_KEY in src/app/lib/api.ts; the mock API answers EXPIRED_TOKEN with a 404.
const TOKEN_KEY = "cruxup.surveyToken";
const EXPIRED_TOKEN = "e2e-expired-token";

test("results list Scarpa Drago as the first ranked shoe", async ({ page }) => {
  await openResults(page);
  await expect(rankedHeadings(page).first()).toHaveText(/^Scarpa Drago/);
});

test("results chart shows the target mark", async ({ page }) => {
  await openResults(page);
  await expect(page.getByRole("img", { name: "Your target" })).toBeVisible();
});

test("the Instinct VS card shows Low confidence", async ({ page }) => {
  await openResults(page);
  await expect(instinctVsCard(page)).toContainText("Low confidence");
});

test("the low-confidence card has a dashed border", async ({ page }) => {
  await openResults(page);
  await expect(instinctVsCard(page)).toHaveCSS("border-top-style", "dashed");
});

test("the Mythos card shows Price unknown", async ({ page }) => {
  await openResults(page);
  await expect(page.getByRole("article", { name: /^La Sportiva Mythos/ })).toContainText("Price unknown");
});

test("a shoe the backend gated out is not on the results page", async ({ page }) => {
  await openResults(page);
  await expect(page.getByText("La Sportiva Miura")).toHaveCount(0);
});

test("the recommend request URL does not contain the survey token", async ({ page }) => {
  const requestPromise = page.waitForRequest(/\/api\/recommend/);
  await submitSurvey(page);
  const request = await requestPromise;
  expect(request.url()).not.toContain("e2e-token");
});

test("an expired survey token shows the not-found message", async ({ page }) => {
  await openResultsWithToken(page, EXPIRED_TOKEN);
  await expect(page.getByText("We couldn't find your survey")).toBeVisible();
});

test("an expired survey token offers a link back to the survey", async ({ page }) => {
  await openResultsWithToken(page, EXPIRED_TOKEN);
  await expect(page.getByRole("link", { name: "Take the survey again" })).toHaveAttribute("href", "/survey");
});

test("results without a survey token link to the survey", async ({ page }) => {
  await page.goto("/results");
  await expect(page.getByRole("link", { name: "Take the survey", exact: true })).toBeVisible();
});

test("results have no horizontal page scroll at 375px", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await openResults(page);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

async function openResults(page: Page) {
  await submitSurvey(page);
  await expect(page.getByRole("heading", { level: 2, name: "Ranked shoes" })).toBeVisible();
}

async function submitSurvey(page: Page) {
  await page.goto("/survey");
  const picker = page.getByRole("combobox", { name: "Shoes that fit you well" });
  await picker.fill("instinct");
  await page.getByRole("option", { name: "Scarpa Instinct VSR (unisex)" }).click();
  await expect(page.getByRole("button", { name: "Remove Scarpa Instinct VSR (unisex)" })).toBeVisible();
  await page.getByRole("button", { name: "Submit answers" }).click();
  await expect(page).toHaveURL(/\/results$/);
}

async function openResultsWithToken(page: Page, token: string) {
  await page.addInitScript(
    ([key, value]) => sessionStorage.setItem(key, value),
    [TOKEN_KEY, token],
  );
  await page.goto("/results");
}

function rankedHeadings(page: Page): Locator {
  return page.getByRole("region", { name: "Ranked shoes" }).getByRole("heading", { level: 3 });
}

// The trailing " (" tells Instinct VS apart from Instinct VSR.
function instinctVsCard(page: Page): Locator {
  return page.getByRole("article", { name: /^Scarpa Instinct VS \(/ });
}
