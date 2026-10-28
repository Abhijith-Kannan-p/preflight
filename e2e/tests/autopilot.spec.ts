import { expect, test, type Page } from "@playwright/test";

const SHOTS = process.env.E2E_SCREENSHOTS;

async function switchTo(page: Page, name: string) {
  await page.locator('[data-tour="role-switcher"] button').first().click();
  await page.getByRole("option", { name: new RegExp(`^${name}`) }).click();
  await expect(page.locator('[data-tour="role-switcher"]')).toContainText(name);
}

// Brand Autopilot: compile the sample brand book, accept a candidate into the rulebook, then
// adopt the Voice Fingerprint learned from the seeded approved history.
test("rulebook compiler and voice fingerprint", async ({ page }) => {
  test.setTimeout(240_000);
  await page.goto("/app/rulebook");
  await switchTo(page, "abhi3");

  await page.getByRole("tab", { name: "Compiler" }).click();
  await page.getByRole("button", { name: "Compile the sample brand book" }).click();
  await expect(page.getByRole("heading", { name: /Review queue/ })).toBeVisible({ timeout: 90_000 });
  const word = page.locator("li", { hasText: "revolutionary" }).filter({ has: page.getByRole("button", { name: "Accept" }) });
  await expect(word).toContainText("Page 9");
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/40-compiler-queue.png`, fullPage: true });
  await word.getByRole("button", { name: "Accept" }).click();
  await expect(page.locator("li", { hasText: "revolutionary" }).first()).toContainText(/accepted → TRM-05/);

  await page.getByRole("tab", { name: "Voice" }).click();
  await expect(page.getByRole("heading", { name: "Hand-set targets and learned fingerprint" })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/Projection/)).toBeVisible();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/41-voice-fingerprint.png`, fullPage: true });
  await page.getByRole("button", { name: "Adopt as targets" }).click();
  await page.getByRole("button", { name: /Create voice profile v2/ }).click();
  await expect(page.getByText("v2 (in use)")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "Earlier voice profiles" })).toBeVisible();

  await page.goto("/app/evaluation");
  await page.getByRole("tab", { name: "Rulebook Compiler" }).click();
  await expect(page.getByRole("cell", { name: "Structured extraction only (LLM down)" })).toBeVisible();
  await expect(page.getByText(/target ≥ 80%/)).toBeVisible();
});
