import { expect, test } from "@playwright/test";

import { brandScore, shot, skipTour, switchTo } from "./helpers";

// J1 Core review: demo → LinkedIn sample → run → margin notes and checklist → accept
// suggestions → re-check → submit → the Approver approves → stamp → certificate with a
// verified audit chain.
test("J1 core review: off-brand LinkedIn post to cleared certificate", async ({ page }) => {
  test.setTimeout(600_000);
  const consoleErrors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => consoleErrors.push(err.message));

  // Landing: two-second splash, then the hero with the demo button.
  await page.goto("/");
  await expect(page.getByRole("status", { name: "Loading Preflight" })).toBeVisible();
  await shot(page, "01-splash", false);
  const demo = page.getByRole("link", { name: "Open the demo desk" }).first();
  await expect(demo).toBeVisible({ timeout: 10_000 });
  await page.waitForTimeout(2200);
  await shot(page, "02-landing", false);
  await demo.click();

  await page.getByRole("button", { name: /LinkedIn post \(off-brand\)/ }).click();
  await expect(page.locator("#draft")).toHaveValue(/India's #1/);
  await shot(page, "03-new-review", false);
  await page.getByRole("button", { name: "Run Preflight" }).click();

  await page.waitForURL(/\/app\/review\/sub_/);
  await expect(page.getByLabel("Critical finding CLM-04", { exact: true })).toBeVisible({ timeout: 300_000 });
  await skipTour(page);
  await expect(page.getByRole("img", { name: /^Brand Score \d+ out of 100$/ }).first()).toBeVisible({ timeout: 300_000 });
  const before = await brandScore(page);
  await shot(page, "04-review", false);
  await expect(page.getByRole("button", { name: "Submit for approval" })).toBeDisabled();

  const acceptButtons = page.getByRole("button", { name: "Accept", exact: true });
  for (let i = 0; i < 12; i++) {
    const remaining = await acceptButtons.count();
    if (remaining === 0) break;
    await acceptButtons.first().click();
    await expect(acceptButtons).toHaveCount(remaining - 1, { timeout: 60_000 });
  }
  const recheck = page.getByRole("button", { name: /Re-check with \d+ change/ });
  await expect(recheck).toBeVisible();
  await recheck.click();
  // Accepting every suggestion already enables Submit on revision 1, so wait for revision 2's
  // own score rather than for the button.
  expect(before).toBeLessThan(50);
  await expect.poll(() => brandScore(page).catch(() => 0), { timeout: 300_000, intervals: [2000] }).toBeGreaterThanOrEqual(90);
  const after = await brandScore(page);
  test.info().annotations.push({ type: "brand score", description: `${before} → ${after}` });
  const submit = page.getByRole("button", { name: "Submit for approval" });
  await expect(submit).toBeEnabled();
  await skipTour(page);
  await shot(page, "05-revision-2", false);
  await submit.click();
  await expect(page.getByText("Holding", { exact: true }).first()).toBeVisible();

  await switchTo(page, "abhi4");
  await expect(page.getByRole("button", { name: "Approve", exact: true }).first()).toBeVisible({ timeout: 20_000 });
  await page.getByRole("button", { name: "Approve", exact: true }).first().click();
  await page.getByRole("dialog").getByRole("button", { name: "Approve" }).click();
  await expect(page.getByText("Cleared", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("img", { name: /Cleared for publication by abhi4/ })).toBeVisible();

  await page.getByRole("link", { name: "View Review Receipt" }).click();
  await expect(page.getByText("Audit chain verified")).toBeVisible();
  await shot(page, "06-receipt", false);
  expect(consoleErrors, consoleErrors.join("\n")).toEqual([]);
});
