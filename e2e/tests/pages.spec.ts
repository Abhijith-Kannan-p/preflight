import { expect, test, type Page } from "@playwright/test";

const SHOTS = process.env.E2E_SCREENSHOTS;

async function shot(page: Page, name: string) {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true });
}

async function switchTo(page: Page, name: string) {
  await page.locator('[data-tour="role-switcher"] button').first().click();
  await page.getByRole("option", { name: new RegExp(`^${name}`) }).click();
  await expect(page.locator('[data-tour="role-switcher"]')).toContainText(name);
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem("preflight.tour.done", "1"));
});

test("admin manages keys, verifies the audit chain and resets the demo", async ({ page }) => {
  await page.goto("/app/settings");
  await switchTo(page, "abhi5");
  await page.getByRole("button", { name: "Create key" }).click();
  await expect(page.getByText("Copy this key now")).toBeVisible();
  await expect(page.locator("pre")).toContainText("pf_live_");
  await page.getByRole("button", { name: "Verify audit chain" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Chain intact" })).toBeVisible();
  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "Reset demo data" }).click();
  await expect(page.getByText("The workspace is back to its starting state")).toBeVisible();
  await shot(page, "10-settings");
});

test("brand manager edits the rulebook; others see it read-only", async ({ page }) => {
  await page.goto("/app/rulebook");
  await expect(page.getByText("Read-only for your role")).toBeVisible();
  await switchTo(page, "abhi3");
  await expect(page.getByRole("button", { name: "New rule" })).toBeVisible();
  await page.getByRole("tab", { name: "Approved facts" }).click();
  await expect(page.getByText("F-086", { exact: true })).toBeVisible();
  await expect(page.getByText("Superseded").first()).toBeVisible();
  await shot(page, "11-rulebook-facts");
  await page.getByRole("tab", { name: "Rules" }).click();
  await shot(page, "12-rulebook-rules");
});

test("insights and evaluation show real numbers", async ({ page }) => {
  await page.goto("/app/insights");
  await switchTo(page, "abhi4");
  await expect(page.getByText("Brand Score over time")).toBeVisible({ timeout: 120_000 });
  await expect(page.getByText("Most violated rules")).toBeVisible();
  await shot(page, "13-insights");
  await page.goto("/app/evaluation");
  await expect(page.getByText("Confusion matrix")).toBeVisible({ timeout: 120_000 });
  await expect(page.getByText("Macro recall")).toBeVisible();
  await expect(page.getByRole("heading", { name: /Held-out check/ })).toBeVisible();
  await shot(page, "14-evaluation");
  await page.getByRole("tab", { name: "Full drafts" }).click();
  await expect(page.getByRole("heading", { name: "Per draft" })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText("Settlement speed").first()).toBeVisible();
  await shot(page, "15-full-drafts");
});
