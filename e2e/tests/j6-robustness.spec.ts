import { expect, test, type Browser, type Page } from "@playwright/test";

import { API, apiGet, switchTo, token } from "./helpers";

interface ReviewItem {
  id: string;
  title: string;
  state: string;
}

async function newVisitor(browser: Browser): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await page.addInitScript(() => window.localStorage.setItem("preflight.tour.done", "1"));
  return page;
}

// J6 Robustness: private sandboxes, refresh mid-review, double-click Run, bad files, wrong-role
// actions, empty states in a fresh sandbox, and five reviews at once.

test("J6 each visitor works in a private sandbox", async ({ browser }) => {
  const alice = await newVisitor(browser);
  const bob = await newVisitor(browser);

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

  await bob.goto("/app");
  bob.once("dialog", (dialog) => dialog.accept());
  await bob.locator('[data-tour="role-switcher"] button').first().click();
  await bob.getByRole("button", { name: "Reset my demo workspace" }).click();
  await alice.goto("/app");
  await expect(alice.getByText("Alice's private draft")).toBeVisible({ timeout: 30_000 });
});

test("J6 refresh mid-review and double-click Run", async ({ browser }) => {
  test.setTimeout(420_000);
  const page = await newVisitor(browser);
  await page.goto("/app/review/new?sample=sample_linkedin");
  await expect(page.locator("#draft")).toHaveValue(/India's #1/, { timeout: 60_000 });
  const title = `Double click ${Date.now()}`;
  await page.locator("#title").fill(title);
  await page.getByRole("button", { name: "Run Preflight" }).dblclick();
  await page.waitForURL(/\/app\/review\/sub_/);

  // Reload straight away: the review is a server-side job and the page reattaches to it.
  await page.reload();
  await expect(page.getByLabel("Critical finding CLM-04", { exact: true })).toBeVisible({ timeout: 300_000 });
  const mine = (await apiGet<ReviewItem[]>(page, "/api/reviews?scope=mine")).filter((r) => r.title === title);
  expect(mine, "a double click starts one review").toHaveLength(1);
});

test("J6 bad files and wrong-role actions get clear messages", async ({ browser }) => {
  const page = await newVisitor(browser);
  await page.goto("/app/review/new");
  await expect(page.getByRole("button", { name: "Run Preflight" })).toBeVisible({ timeout: 60_000 });
  const cases: { name: string; mimeType: string; buffer: Buffer; message: RegExp }[] = [
    { name: "empty.pdf", mimeType: "application/pdf", buffer: Buffer.alloc(0), message: /empty|could not be opened|No readable text/i },
    { name: "renamed.pdf", mimeType: "application/pdf", buffer: Buffer.from([0x4d, 0x5a, 0x90, 0x00, 0x03, 0x00, 0xff, 0xfe]), message: /could not be opened|not a|valid PDF/i },
    { name: "broken.docx", mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", buffer: Buffer.from("not a zip"), message: /could not be opened|valid Word/i },
  ];
  for (const c of cases) {
    await page.locator('input[type="file"]').setInputFiles({ name: c.name, mimeType: c.mimeType, buffer: c.buffer });
    await page.getByRole("button", { name: "Run Preflight" }).click();
    await expect(page.getByText(c.message).first()).toBeVisible({ timeout: 30_000 });
    await expect(page).toHaveURL(/\/app\/review\/new/);
    await expect(page.getByText(/Traceback|Internal Server Error/)).toHaveCount(0);
  }

  // A creator cannot approve or edit the rulebook: the UI says so and the API refuses politely.
  await page.goto("/app/settings");
  await expect(page.getByText(/managed by the admin/)).toBeVisible({ timeout: 30_000 });
  await page.goto("/app/rulebook");
  await expect(page.getByText("Read-only for your role")).toBeVisible();
  const reviews = await apiGet<ReviewItem[]>(page, "/api/reviews?scope=all");
  const waiting = reviews.find((r) => r.state === "in_review");
  expect(waiting, "the demo history has a draft awaiting approval").toBeTruthy();
  const denied = await page.request.post(`${API}/api/reviews/${waiting!.id}/transition`, {
    headers: { Authorization: `Bearer ${await token(page)}`, "Content-Type": "application/json" },
    data: { action: "approve" },
  });
  expect(denied.status()).toBe(403);
  expect((await denied.json()).detail).toMatch(/Approver|approve/i);
});

test("J6 a fresh sandbox shows helpful empty states", async ({ browser }) => {
  const page = await newVisitor(browser);
  await page.goto("/app/rulebook");
  await switchTo(page, "abhi3");
  await page.getByRole("tab", { name: "Compiler" }).click();
  await expect(page.getByText("No brand book compiled yet")).toBeVisible();
  await page.goto("/app/governance");
  await page.getByRole("tab", { name: "Stale-Content Radar" }).click();
  await expect(page.getByText("Nothing stale")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("button", { name: "Simulate fact update on F-087" })).toBeVisible();
  await page.goto("/app/settings");
  await switchTo(page, "abhi5");
  await expect(page.getByText("No webhooks yet")).toBeVisible();
});

test("J6 five reviews at once all complete", async ({ browser }) => {
  test.setTimeout(600_000);
  const visitors = await Promise.all(Array.from({ length: 5 }, () => newVisitor(browser)));
  await Promise.all(
    visitors.map(async (page) => {
      await page.goto("/app/review/new?sample=sample_linkedin");
      await expect(page.locator("#draft")).toHaveValue(/India's #1/, { timeout: 120_000 });
    }),
  );
  const started = Date.now();
  const durations = await Promise.all(
    visitors.map(async (page, i) => {
      await page.locator("#title").fill(`Concurrent ${i + 1}`);
      // Unique text per visitor, so no result comes from the review cache.
      const draft = page.locator("#draft");
      await draft.fill(`${await draft.inputValue()} Ref ${Date.now()}-${i + 1}.`);
      await page.getByRole("button", { name: "Run Preflight" }).click();
      await page.waitForURL(/\/app\/review\/sub_/, { timeout: 60_000 });
      await expect(page.getByRole("img", { name: /^Brand Score \d+ out of 100$/ }).first()).toBeVisible({ timeout: 540_000 });
      return Math.round((Date.now() - started) / 1000);
    }),
  );
  test.info().annotations.push({ type: "completed after (s)", description: durations.sort((a, b) => a - b).join(", ") });
  console.log(`five concurrent reviews completed after ${durations.join(", ")} s`);
  expect(durations).toHaveLength(5);
});
