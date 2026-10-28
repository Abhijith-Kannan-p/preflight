import { expect, test, type Page } from "@playwright/test";

const SHOTS = process.env.E2E_SCREENSHOTS;
const API = process.env.E2E_API_URL ?? "http://localhost:8000";

async function switchTo(page: Page, name: string) {
  await page.locator('[data-tour="role-switcher"] button').first().click();
  await page.getByRole("option", { name: new RegExp(`^${name}`) }).click();
  await expect(page.locator('[data-tour="role-switcher"]')).toContainText(name);
}

// Webhook delivery log and Resend. The target is the API's own /health, which answers a POST
// with 405: a client error, so the delivery fails at once without retries (no outside network).
test("webhook events, delivery log and resend", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto("/app/settings");
  await switchTo(page, "abhi5");
  await page.getByLabel("Webhook URL").fill(`${API}/health`);
  await expect(page.getByLabel(/^Critical finding/).first()).toBeChecked();
  await page.getByRole("button", { name: "Add webhook" }).click();
  await page.getByRole("button", { name: "Send test event" }).click();
  await expect(page.getByText("HTTP 405").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("cell", { name: /^failed/ }).first()).toBeVisible();
  await page.getByRole("button", { name: /^Resend delivery/ }).first().click();
  await expect(page.getByText(/resend of #\d+/)).toBeVisible({ timeout: 30_000 });
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/50-webhooks.png`, fullPage: true });
});

test("full-draft evaluation and held-out claims", async ({ page }) => {
  await page.goto("/app/evaluation");
  await page.getByRole("tab", { name: "Full drafts" }).click();
  await expect(page.getByRole("heading", { name: "Per draft" })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText("Settlement speed").first()).toBeVisible();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/51-full-drafts.png`, fullPage: true });
  await page.getByRole("tab", { name: "Claim Ledger" }).click();
  await expect(page.getByRole("heading", { name: /Held-out check/ })).toBeVisible({ timeout: 60_000 });
});
