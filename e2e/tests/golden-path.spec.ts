import { expect, test, type Page } from "@playwright/test";

const SHOTS = process.env.E2E_SCREENSHOTS;

async function shot(page: Page, name: string) {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: false });
}

async function skipTour(page: Page) {
  const skip = page.getByRole("button", { name: "Skip tour" });
  if (await skip.isVisible().catch(() => false)) await skip.click();
}

test("golden path: LinkedIn draft to approved receipt", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") {
      consoleErrors.push(msg.text());
      console.log("[browser error]", msg.text());
    }
  });
  page.on("pageerror", (err) => consoleErrors.push(err.message));

  // Landing: two-second splash, then the hero with the demo button.
  await page.goto("/");
  await expect(page.getByRole("status", { name: "Loading Preflight" })).toBeVisible();
  await shot(page, "01-splash");
  const demo = page.getByRole("link", { name: "Open the demo desk" }).first();
  await expect(demo).toBeVisible({ timeout: 10_000 });
  await page.waitForTimeout(2200);
  await shot(page, "02-landing");
  await demo.click();

  // New review: pick the Round 1 LinkedIn sample and run.
  await page.getByRole("button", { name: /LinkedIn post \(off-brand\)/ }).click();
  await expect(page.locator("#draft")).toHaveValue(/India's #1/);
  await shot(page, "03-new-review");
  await page.getByRole("button", { name: "Run Preflight" }).click();

  // Review workspace: wait for the margin notes, see CLM-04 critical.
  await page.waitForURL(/\/app\/review\/sub_/);
  await expect(page.getByLabel("Critical finding CLM-04", { exact: true })).toBeVisible({ timeout: 300_000 });
  await skipTour(page);
  await shot(page, "04-review");
  await expect(page.getByRole("button", { name: "Submit for approval" })).toBeDisabled();

  // Accept every suggestion, then re-check.
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
  await expect(page.getByText("revision 2", { exact: false }).first()).toBeVisible({ timeout: 30_000 });
  const submit = page.getByRole("button", { name: "Submit for approval" });
  await expect(submit).toBeEnabled({ timeout: 300_000 });
  await skipTour(page);
  await shot(page, "05-revision-2");
  await submit.click();
  await expect(page.getByText("Holding", { exact: true }).first()).toBeVisible();

  // Switch to abhi4 (Approver) and approve.
  await page.locator('[data-tour="role-switcher"] button').first().click();
  await page.getByRole("option", { name: /abhi4/ }).click();
  await expect(page.getByRole("button", { name: "Approve", exact: true }).first()).toBeVisible({ timeout: 20_000 });
  await page.getByRole("button", { name: "Approve", exact: true }).first().click();
  await page.getByRole("dialog").getByRole("button", { name: "Approve" }).click();
  await expect(page.getByText("Cleared", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("img", { name: /Cleared for publication by abhi4/ })).toBeVisible();

  // Receipt with a verified audit chain.
  await page.getByRole("link", { name: "View Review Receipt" }).click();
  await expect(page.getByText("Audit chain verified")).toBeVisible();
  await shot(page, "06-receipt");
  expect(consoleErrors, consoleErrors.join("\n")).toEqual([]);
});
