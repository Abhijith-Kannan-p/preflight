import { expect, test } from "@playwright/test";

// Two visitors (separate browser contexts, so separate cookies) get separate sandboxes:
// one visitor's review never appears for the other, and a reset touches only its owner.
test("each visitor works in a private sandbox", async ({ browser }) => {
  const alice = await (await browser.newContext()).newPage();
  const bob = await (await browser.newContext()).newPage();

  await alice.goto("/app/review/new?sample=sample_clean");
  await expect(alice.locator("#draft")).toHaveValue(/PayWise/, { timeout: 60_000 });
  await alice.locator("#title").fill("Alice's private draft");
  await alice.getByRole("button", { name: "Run Preflight" }).click();
  await alice.waitForURL(/\/app\/review\/sub_/);
  const aliceReview = alice.url();

  await bob.goto("/app");
  await expect(bob.getByRole("heading", { name: /Welcome/ })).toBeVisible({ timeout: 60_000 });
  await expect(bob.getByText("Alice's private draft")).toHaveCount(0);
  await bob.goto(aliceReview);
  await expect(bob.getByRole("heading", { name: "This review is not in your workspace" })).toBeVisible({ timeout: 30_000 });

  // Bob resets his sandbox from the role switcher; Alice's draft survives.
  await bob.goto("/app");
  bob.once("dialog", (dialog) => dialog.accept());
  await bob.locator('[data-tour="role-switcher"] button').first().click();
  await bob.getByRole("button", { name: "Reset my demo workspace" }).click();
  await alice.goto("/app");
  await expect(alice.getByText("Alice's private draft")).toBeVisible({ timeout: 30_000 });
});
