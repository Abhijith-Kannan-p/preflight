import { expect, test } from "@playwright/test";

import { apiGet, shot, switchTo } from "./helpers";

interface Health {
  rules: { code: string; version: number; flagged: boolean }[];
}

// J3 Governance: Guideline Health → suggest rewording → publish a new rule version; simulate a
// fact update on F-087 → the Radar lists affected items → re-check one; the Creator Coach shows
// abhi1's recurring issues on New review.
test("J3 governance: rewording, stale-content radar and coach", async ({ page }) => {
  test.setTimeout(300_000);
  await page.goto("/app/governance");
  await switchTo(page, "abhi3");

  await expect(page.getByRole("heading", { name: /Flagged as ambiguous/ })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText("No guaranteed-outcome language").first()).toBeVisible();
  await expect(page.getByText(/target met/)).toBeVisible();
  await shot(page, "30-guideline-health");

  const flagged = (await apiGet<Health>(page, "/api/governance/health")).rules.find((r) => r.flagged);
  expect(flagged, "a flagged rule").toBeTruthy();
  await page.getByRole("button", { name: "Suggest clearer wording" }).first().click();
  await page.getByRole("button", { name: /Suggest clearer wording from the/ }).click();
  await expect(page.getByLabel("New description")).not.toBeEmpty({ timeout: 60_000 });
  await page.getByRole("button", { name: /^Publish as version/ }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0, { timeout: 30_000 });
  const after = (await apiGet<Health>(page, "/api/governance/health")).rules.find((r) => r.code === flagged!.code);
  expect(after?.version).toBe(flagged!.version + 1);

  await page.getByRole("navigation", { name: "Governance sections" }).getByRole("link", { name: "Stale-Content Radar" }).click();
  await expect(page.getByText("Nothing stale")).toBeVisible();
  await page.getByRole("button", { name: "Simulate fact update on F-087" }).click();
  // Supersedes the fact and re-indexes every cleared item: about 20 s on the free hosting.
  await expect(page.getByRole("button", { name: "Re-check now" }).first()).toBeVisible({ timeout: 120_000 });
  await expect(page.getByText("PayWise settles merchant payments in under 15 seconds.").first()).toBeVisible();
  await shot(page, "31-radar");
  await page.getByRole("button", { name: "Re-check now" }).first().click();
  await page.waitForURL(/\/app\/review\/sub_/, { timeout: 30_000 });
  await expect(page.getByLabel(/finding CLM-03$/).first()).toBeVisible({ timeout: 300_000 });

  await page.goto("/app/governance");
  await page.getByRole("navigation", { name: "Governance sections" }).getByRole("link", { name: "Creator Coach" }).click();
  await expect(page.getByRole("heading", { name: "Before your next draft" })).toBeVisible();
  await shot(page, "32-coach");

  await switchTo(page, "abhi1");
  await page.goto("/app/review/new");
  await expect(page.getByRole("heading", { name: /Your coach/ })).toBeVisible({ timeout: 30_000 });
});
