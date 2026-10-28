import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

const SHOTS = process.env.E2E_SCREENSHOTS;
const FIXED = fileURLToPath(new URL("../../data/seed/files/paywise_clean_visual.png", import.meta.url));

// Visual and accessibility review: the festive banner sample, its notes on the image, then a
// corrected design uploaded as the next revision.
test("visual review of an image, then a corrected version", async ({ page }) => {
  test.setTimeout(420_000);
  await page.goto("/app/review/new");
  await page.getByRole("button", { name: /Festive banner \(image\)/ }).click();
  await expect(page.getByLabel("Alt text for this image")).toHaveValue("image of banner.png");
  await page.getByRole("button", { name: "Run Preflight" }).click();
  await page.waitForURL(/\/app\/review\/sub_/);

  await expect(page.getByLabel("Major finding VIS-01", { exact: true })).toBeVisible({ timeout: 300_000 });
  const skip = page.getByRole("button", { name: "Skip tour" });
  if (await skip.isVisible().catch(() => false)) await skip.click();
  await expect(page.getByLabel("Major finding ACC-01", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Critical finding CLM-04", { exact: true })).toBeVisible();
  await expect(page.getByRole("img", { name: "The reviewed visual" })).toBeVisible();
  await expect(page.getByText("off-palette").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Major finding VIS-01 on the image" })).toBeVisible();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/20-visual-review.png`, fullPage: true });

  await page.locator('input[type="file"]').setInputFiles(FIXED);
  await expect(page.getByText("revision 2", { exact: false }).first()).toBeVisible({ timeout: 60_000 });
  // The corrected design clears the visual and claim issues. (The weak alt text carries over to
  // the new version, so ACC-03 stays until the alt text is fixed.)
  await expect(page.getByLabel("Major finding ACC-03", { exact: true }).or(page.getByLabel("Minor finding ACC-03", { exact: true }))).toBeVisible({ timeout: 300_000 });
  for (const rule of ["VIS-01", "ACC-01", "CLM-04"]) {
    await expect(page.getByLabel(new RegExp(`finding ${rule}$`))).toHaveCount(0);
  }
});
