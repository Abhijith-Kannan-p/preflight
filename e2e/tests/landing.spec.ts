import { expect, test } from "@playwright/test";

test("landing explains the product after the splash", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "How it works" })).toBeAttached();
  await page.waitForTimeout(2300); // two-second splash
  const how = page.locator("#how-it-works");
  await how.scrollIntoViewIfNeeded();
  await expect(how.getByRole("listitem")).toHaveCount(4);
  if (process.env.E2E_SCREENSHOTS) await how.screenshot({ path: `${process.env.E2E_SCREENSHOTS}/07-how-it-works.png` });
});
