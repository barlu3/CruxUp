import { expect, test } from "@playwright/test";

test("home page links through to the survey", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle("CruxUp");
  await expect(page.getByRole("heading", { level: 1, name: "CruxUp" })).toBeVisible();
  await page.getByRole("link", { name: /start the questionnaire/i }).click();
  await expect(page).toHaveURL(/\/survey$/);
});
