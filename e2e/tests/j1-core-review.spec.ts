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

  // Landing: the murmuration hero with the demo button.
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Every claim earns its place." })).toBeVisible();
  const demo = page.getByRole("link", { name: "Open the demo desk" }).first();
  await expect(demo).toBeInViewport({ timeout: 10_000 });
  await shot(page, "01-landing", false);
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
  // After the re-check every note left on the new revision is joined to its mark.
  await expect.poll(async () => (await page.locator("[data-connector]").count()) - (await page.locator("[data-note]").count())).toBe(0);
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

// "Accept all suggested fixes" accepts every open suggestion at once (one request per note,
// each with its own idempotency key), exactly as pressing every Accept would.
test("J1 accept all suggested fixes, numbered notes and filters", async ({ page }) => {
  test.setTimeout(420_000);
  await page.addInitScript(() => window.localStorage.setItem("preflight.tour.done", "1"));
  await page.goto("/app/review/new?sample=sample_linkedin");
  await expect(page.locator("#draft")).toHaveValue(/India's #1/, { timeout: 60_000 });
  await page.locator("#draft").fill(`${await page.locator("#draft").inputValue()} Ref ${Date.now()}.`);
  await page.getByRole("button", { name: "Run Preflight" }).click();
  await page.waitForURL(/\/app\/review\/sub_/);
  await expect(page.getByLabel("Critical finding CLM-04", { exact: true })).toBeVisible({ timeout: 300_000 });

  const summary = page.getByRole("region", { name: "Proof summary" });
  await expect(summary).toContainText("Not ready to publish");
  // Severity filter hides and restores the critical notes.
  await summary.getByRole("button", { name: /critical/ }).click();
  await expect(page.getByLabel("Critical finding CLM-04", { exact: true })).toHaveCount(0);
  await summary.getByRole("button", { name: /critical/ }).click();
  await expect(page.getByLabel("Critical finding CLM-04", { exact: true })).toBeVisible();

  const acceptAll = summary.getByRole("button", { name: /Accept all suggested fixes/ });
  const fixable = Number((await acceptAll.innerText()).match(/(\d+)\s*$/)?.[1]);
  expect(fixable).toBeGreaterThan(0);
  await acceptAll.dblclick(); // a double click must still accept each fix once
  await expect(page.getByRole("button", { name: new RegExp(`Re-check with ${fixable} change`) })).toBeVisible({ timeout: 60_000 });
  await expect(summary.getByRole("button", { name: /Accept all suggested fixes/ })).toHaveCount(0);
});
