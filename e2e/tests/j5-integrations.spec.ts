import { expect, test } from "@playwright/test";

import { API, shot, switchTo } from "./helpers";

// J5 Integrations: Admin → create an API key → the curl example works → webhooks with
// retries, the delivery log and Resend. Webhook targets need no outside network:
// - the API's own /health answers a POST with 405, a client error: failed at once, no retries;
// - 127.0.0.1:9 refuses connections: retried twice (after 2 s and 4 s), then failed.
test("J5 integrations: API key, curl example, webhooks with retries and resend", async ({ page }) => {
  test.setTimeout(180_000);
  await page.goto("/app/settings");
  await switchTo(page, "abhi5");

  await page.getByRole("button", { name: "Create key" }).click();
  await expect(page.getByText("Copy this key now")).toBeVisible();
  const curl = await page.locator("pre").first().innerText();
  const key = curl.match(/pf_live_[A-Za-z0-9_-]+/)?.[0];
  expect(key, "the curl example carries the new key").toBeTruthy();
  // The same request the curl example makes.
  const call = () =>
    page.request.post(`${API}/api/v1/preflight`, {
      headers: { "X-API-Key": key!, "Content-Type": "application/json" },
      data: { content: "PayWise is 100% secure!", channel: "linkedin" },
      timeout: 120_000,
    });
  // A reused keep-alive connection can be reset by the host's proxy; a client retries that once.
  const response = await call().catch(call);
  expect(response.status()).toBe(200);
  const result = await response.json();
  expect(result.blocking).toBe(true);
  expect(JSON.stringify(result.findings)).toContain("CLM-04");

  await page.getByLabel("Webhook URL").fill(`${API}/health`);
  await expect(page.getByLabel(/^Critical finding/).first()).toBeChecked();
  await page.getByRole("button", { name: "Add webhook" }).click();
  const health = page.locator("div.rounded-xl", { hasText: `${API}/health` });
  await health.getByRole("button", { name: "Send test event" }).click();
  await expect(health.getByText("HTTP 405").first()).toBeVisible({ timeout: 30_000 });
  await expect(health.getByRole("cell", { name: /^failed/ }).first()).toBeVisible();
  await expect(health.getByRole("cell", { name: /^1 \/ 3/ }).first()).toBeVisible();
  await health.getByRole("button", { name: /^Resend delivery/ }).first().click();
  await expect(health.getByText(/resend of #\d+/)).toBeVisible({ timeout: 30_000 });

  await page.getByLabel("Webhook URL").fill("http://127.0.0.1:9/hook");
  await page.getByRole("button", { name: "Add webhook" }).click();
  const refused = page.locator("div.rounded-xl", { hasText: "127.0.0.1:9/hook" });
  await refused.getByRole("button", { name: "Send test event" }).click();
  await expect(refused.getByRole("cell", { name: /^retrying/ }).first()).toBeVisible({ timeout: 30_000 });
  await expect(refused.getByRole("cell", { name: /^3 \/ 3/ }).first()).toBeVisible({ timeout: 60_000 });
  await expect(refused.getByRole("cell", { name: /^failed/ }).first()).toBeVisible();
  await shot(page, "50-webhooks");
});
