import { expect, test } from "@playwright/test";

test("home page links through to the survey", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle("CruxUp");
  await expect(page.getByRole("heading", { level: 1, name: "CruxUp" })).toBeVisible();
  await page.getByRole("link", { name: /start the questionnaire/i }).click();
  await expect(page).toHaveURL(/\/survey$/);
});

// A 404 also lands on /survey, so the URL check alone cannot catch a missing
// route. W6-1 replaces this with an assertion on the questionnaire itself.
test("survey route is served", async ({ request }) => {
  const response = await request.get("/survey");
  expect(response.status()).toBe(200);
});
