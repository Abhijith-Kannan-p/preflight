import { expect, type Page } from "@playwright/test";

/** Where the API runs. Locally the backend; against production the Render URL. */
export const API = (process.env.E2E_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
const SHOTS = process.env.E2E_SCREENSHOTS;

export async function shot(page: Page, name: string, fullPage = true) {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage });
}

export async function switchTo(page: Page, name: string) {
  await page.locator('[data-tour="role-switcher"] button').first().click();
  await page.getByRole("option", { name: new RegExp(`^${name}`) }).click();
  await expect(page.locator('[data-tour="role-switcher"]')).toContainText(name);
}

export async function skipTour(page: Page) {
  const skip = page.getByRole("button", { name: "Skip tour" });
  if (await skip.isVisible().catch(() => false)) await skip.click();
}

/** The current demo user's signed token, as the app stores it. */
export async function token(page: Page): Promise<string> {
  const value = await page.evaluate(() => window.localStorage.getItem("preflight.token"));
  expect(value, "signed in").toBeTruthy();
  return value as string;
}

/** Call the API as the current demo user. */
export async function apiGet<T>(page: Page, path: string): Promise<T> {
  const response = await page.request.get(`${API}${path}`, { headers: { Authorization: `Bearer ${await token(page)}` } });
  expect(response.ok(), `${path} → ${response.status()}`).toBeTruthy();
  return (await response.json()) as T;
}

export async function brandScore(page: Page): Promise<number> {
  const label = await page.getByRole("img", { name: /^Brand Score \d+ out of 100$/ }).first().getAttribute("aria-label");
  return Number(label?.match(/\d+/)?.[0]);
}
