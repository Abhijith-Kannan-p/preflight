import { expect, test } from "@playwright/test";

import { apiGet, shot, switchTo } from "./helpers";

interface Fingerprint {
  learned: Record<string, { value: number }>;
}

/** The first `tone` object anywhere in a review payload. */
function findTone(value: unknown): { targets: Record<string, number> } | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  if (record.tone && typeof record.tone === "object") return record.tone as { targets: Record<string, number> };
  for (const child of Object.values(record)) {
    const found = findTone(child);
    if (found) return found;
  }
  return null;
}

// J4 Autopilot: Brand Manager → Rulebook Compiler → sample brand book → live extraction →
// accept a candidate → rule active; Voice Fingerprint → adopt → the next tone check uses it.
test("J4 autopilot: compile the brand book, adopt the voice fingerprint", async ({ page }) => {
  test.setTimeout(420_000);
  await page.goto("/app/rulebook");
  await switchTo(page, "abhi3");

  await page.getByRole("tab", { name: "Compiler" }).click();
  await page.getByRole("button", { name: "Compile the sample brand book" }).click();
  await expect(page.getByRole("heading", { name: /Review queue/ })).toBeVisible({ timeout: 120_000 });
  const word = page.locator("li", { hasText: "revolutionary" }).filter({ has: page.getByRole("button", { name: "Accept" }) });
  await expect(word).toContainText("Page 9");
  await shot(page, "40-compiler-queue");
  await word.getByRole("button", { name: "Accept" }).click();
  await expect(page.locator("li", { hasText: "revolutionary" }).first()).toContainText(/accepted → TRM-05/);
  await page.getByRole("tab", { name: "Terminology" }).click();
  await expect(page.getByText("revolutionary", { exact: true })).toBeVisible();

  await page.getByRole("tab", { name: "Voice" }).click();
  await expect(page.getByRole("heading", { name: "Hand-set targets and learned fingerprint" })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/Projection/)).toBeVisible();
  await shot(page, "41-voice-fingerprint");
  const fingerprint = await apiGet<Fingerprint>(page, "/api/voice/fingerprint");
  await page.getByRole("button", { name: "Adopt as targets" }).click();
  await page.getByRole("button", { name: /Create voice profile v2/ }).click();
  await expect(page.getByText("v2 (in use)")).toBeVisible({ timeout: 30_000 });

  // The next review compares tone with the adopted targets.
  await page.goto("/app/review/new?sample=sample_clean");
  await expect(page.locator("#draft")).toHaveValue(/PayWise/, { timeout: 60_000 });
  await page.locator("#title").fill("Tone after adoption");
  await page.getByRole("button", { name: "Run Preflight" }).click();
  await page.waitForURL(/\/app\/review\/sub_/);
  const id = page.url().split("/").pop()!;
  await expect(page.getByRole("img", { name: /^Brand Score \d+ out of 100$/ }).first()).toBeVisible({ timeout: 300_000 });
  const tone = findTone(await apiGet<unknown>(page, `/api/reviews/${id}`));
  const learned = Object.fromEntries(Object.entries(fingerprint.learned).map(([t, v]) => [t, v.value]));
  expect(tone?.targets).toEqual(learned);

  await page.goto("/app/evaluation");
  await page.getByRole("tab", { name: "Rulebook Compiler" }).click();
  await expect(page.getByRole("cell", { name: "Structured extraction only (LLM down)" })).toBeVisible();
  await expect(page.getByText(/target ≥ 80%/)).toBeVisible();
});
