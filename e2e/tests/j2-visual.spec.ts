import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

import { shot, skipTour, switchTo } from "./helpers";

const FIXED = fileURLToPath(new URL("../../data/seed/files/paywise_clean_visual.png", import.meta.url));

// J2 Visual: festive banner sample → OCR text, palette, contrast and claim findings on the
// image → a corrected design as the next revision → approve.
test("J2 visual: festive banner to an approved corrected design", async ({ page }) => {
  test.setTimeout(600_000);
  await page.goto("/app/review/new");
  await page.getByRole("button", { name: /Festive banner \(image\)/ }).click();
  await expect(page.getByLabel("Alt text for this image")).toHaveValue("image of banner.png");
  await page.getByRole("button", { name: "Run Preflight" }).click();
  await page.waitForURL(/\/app\/review\/sub_/);

  await expect(page.getByLabel("Major finding VIS-01", { exact: true })).toBeVisible({ timeout: 300_000 });
  await skipTour(page);
  await expect(page.getByLabel("Major finding ACC-01", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Critical finding CLM-04", { exact: true })).toBeVisible();
  await expect(page.getByRole("img", { name: "The reviewed visual" })).toBeVisible();
  await expect(page.getByText("off-palette").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Major finding VIS-01 on the image" })).toBeVisible();
  await shot(page, "20-visual-review");

  await page.locator('input[type="file"]').setInputFiles(FIXED);
  await expect(page.getByText("revision 2", { exact: false }).first()).toBeVisible({ timeout: 60_000 });
  // The corrected design clears the visual and claim issues. The weak alt text carries over,
  // so ACC-03 (minor) remains until the alt text is fixed; it does not block approval.
  await expect(page.getByLabel(/finding ACC-03$/)).toBeVisible({ timeout: 300_000 });
  for (const rule of ["VIS-01", "ACC-01", "CLM-04"]) {
    await expect(page.getByLabel(new RegExp(`finding ${rule}$`))).toHaveCount(0);
  }

  const submit = page.getByRole("button", { name: "Submit for approval" });
  await expect(submit).toBeEnabled({ timeout: 60_000 });
  await submit.click();
  await switchTo(page, "abhi4");
  await page.getByRole("button", { name: "Approve", exact: true }).first().click();
  await page.getByRole("dialog").getByRole("button", { name: "Approve" }).click();
  await expect(page.getByRole("img", { name: /Cleared for publication by abhi4/ })).toBeVisible();
  await shot(page, "21-visual-cleared");
});
