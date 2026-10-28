import { expect, test, type Page } from "@playwright/test";

const SHOTS = process.env.E2E_SCREENSHOTS;

async function switchTo(page: Page, name: string) {
  await page.locator('[data-tour="role-switcher"] button').first().click();
  await page.getByRole("option", { name: new RegExp(`^${name}`) }).click();
  await expect(page.locator('[data-tour="role-switcher"]')).toContainText(name);
}

// Governance intelligence on the seeded history: an ambiguous rule on the Guideline Health
// board, a simulated fact change that lands on the Stale-Content Radar, and the Coach.
test("guideline health, stale-content radar and creator coach", async ({ page }) => {
  test.setTimeout(240_000);
  await page.goto("/app/governance");
  await switchTo(page, "abhi3");

  await expect(page.getByRole("heading", { name: /Flagged as ambiguous/ })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText("No guaranteed-outcome language").first()).toBeVisible();
  await expect(page.getByText(/target met/)).toBeVisible();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/30-guideline-health.png`, fullPage: true });

  await page.getByRole("button", { name: "Suggest clearer wording" }).first().click();
  await page.getByRole("button", { name: /Suggest clearer wording from the/ }).click();
  await expect(page.getByLabel("New description")).not.toBeEmpty({ timeout: 60_000 });
  await page.getByRole("button", { name: "Cancel" }).click();

  await page.getByRole("tab", { name: "Stale-Content Radar" }).click();
  await expect(page.getByText("Nothing stale")).toBeVisible();
  await page.getByRole("button", { name: "Simulate fact update on F-087" }).click();
  await expect(page.getByRole("button", { name: "Re-check now" }).first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("PayWise settles merchant payments in under 15 seconds.").first()).toBeVisible();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/31-radar.png`, fullPage: true });

  await page.getByRole("tab", { name: "Creator Coach" }).click();
  await expect(page.getByRole("heading", { name: "Before your next draft" })).toBeVisible();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/32-coach.png`, fullPage: true });
});
