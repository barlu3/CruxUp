import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

// The fake backend rejects exactly this budget with a 422.
const REJECTED_BUDGET = "1";

test("survey page shows the questionnaire heading", async ({ page }) => {
  await page.goto("/survey");
  await expect(
    page.getByRole("heading", { level: 1, name: "Find your climbing shoe" }),
  ).toBeVisible();
});

test("submitting with a picked good-fit shoe lands on results", async ({ page }) => {
  await pickGoodFitShoe(page);
  await page.getByRole("button", { name: "Find my shoes" }).click();
  await expect(page).toHaveURL(/\/results$/);
});

test("results list the ranked shoes after submitting", async ({ page }) => {
  await pickGoodFitShoe(page);
  await page.getByRole("button", { name: "Find my shoes" }).click();
  await expect(page.getByRole("heading", { level: 2, name: "Ranked shoes" })).toBeVisible();
});

test("survey token is not exposed in the URL after submit", async ({ page }) => {
  await pickGoodFitShoe(page);
  await page.getByRole("button", { name: "Find my shoes" }).click();
  await expect(page).toHaveURL(/\/results$/);
  expect(page.url()).not.toContain("e2e-token");
});

test("a server rejection is shown in the error region", async ({ page }) => {
  await page.goto("/survey");
  await page.getByLabel("Budget (USD)").fill(REJECTED_BUDGET);
  await page.getByRole("button", { name: "Find my shoes" }).click();
  await expect(
    page.getByRole("region", { name: "We couldn't save your survey" }),
  ).toContainText("budget_cap_usd=1 is below the minimum");
});

test("a server rejection keeps the user on the survey", async ({ page }) => {
  await page.goto("/survey");
  await page.getByLabel("Budget (USD)").fill(REJECTED_BUDGET);
  await page.getByRole("button", { name: "Find my shoes" }).click();
  await expect(page.getByRole("region", { name: "We couldn't save your survey" })).toBeVisible();
  await expect(page).toHaveURL(/\/survey$/);
});

async function pickGoodFitShoe(page: Page) {
  await page.goto("/survey");
  const picker = page.getByRole("combobox", { name: "Shoes that fit you well" });
  await picker.fill("instinct");
  await page.getByRole("option", { name: "Scarpa Instinct VSR (unisex)" }).click();
  await expect(
    page.getByRole("button", { name: "Remove Scarpa Instinct VSR (unisex)" }),
  ).toBeVisible();
}
