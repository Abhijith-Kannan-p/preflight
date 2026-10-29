// The README and handover screenshots: nine scenes at 1440 × 900 in Night Desk and Paper Desk.
// Usage: node scripts/readme-shots.mjs <frontend URL> <API URL> <out dir>
import { chromium } from "playwright";

const [WEB = "http://localhost:3000", API = "http://127.0.0.1:8000", OUT = "."] = process.argv.slice(2);
const browser = await chromium.launch();

async function switchTo(page, name) {
  await page.locator('[data-tour="role-switcher"] button').first().click();
  await page.getByRole("option", { name: new RegExp(`^${name}`) }).click();
  await page.waitForTimeout(1500);
}

async function settle(page) {
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.waitForTimeout(900);
}

async function runSample(page, sample) {
  await page.goto(`${WEB}/app/review/new?sample=${sample}`);
  const run = page.getByRole("button", { name: "Run Preflight" });
  await run.waitFor({ timeout: 120_000 });
  await page.waitForFunction(() => [...document.querySelectorAll("button")].some((b) => b.textContent?.includes("Run Preflight") && !b.disabled), null, { timeout: 120_000 });
  await page.waitForTimeout(500);
  await run.click();
  await page.waitForURL(/\/app\/review\/sub_/);
  await page.getByRole("img", { name: /^Brand Score \d+/ }).first().waitFor({ timeout: 300_000 });
  await settle(page);
}

for (const scheme of ["dark", "light"]) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: scheme });
  const page = await context.newPage();
  await page.addInitScript(() => localStorage.setItem("preflight.tour.done", "1"));
  const shot = (name) => page.screenshot({ path: `${OUT}/${name}-${scheme}.png` });

  // Intro frame and the landing page.
  await page.goto(`${WEB}/`);
  await page.getByRole("heading", { name: "Every claim, cleared." }).waitFor();
  await page.evaluate(() => window.scrollTo(0, 0.5 * (document.querySelector(".intro-stage").offsetHeight - innerHeight)));
  await page.mouse.move(820, 380);
  await page.waitForTimeout(900);
  await shot("intro");
  await page.getByRole("button", { name: "Skip intro" }).first().click();
  await page.waitForTimeout(1200);
  await shot("landing");

  // A review, then its proof sheet with numbered notes (note 2 open, note 1 pointed at).
  await runSample(page, "sample_linkedin");
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(400);
  await shot("review");
  await page.locator("[data-note]").nth(1).click();
  await page.locator('[aria-label="Proof summary"]').scrollIntoViewIfNeeded();
  await page.evaluate(() => window.scrollBy(0, -90));
  await page.locator("[data-note]").first().hover();
  await page.waitForTimeout(600);
  await shot("proof-sheet");

  // Visual review: the banner with numbered boxes.
  await runSample(page, "sample_festive_banner");
  await page.getByRole("img", { name: "The reviewed visual" }).scrollIntoViewIfNeeded();
  await page.evaluate(() => window.scrollBy(0, -220));
  await page.waitForTimeout(500);
  await shot("visual-review");

  // Governance, Compiler and Voice as the brand manager.
  await page.goto(`${WEB}/app/governance`);
  await page.locator('[data-tour="role-switcher"] button').first().waitFor({ timeout: 90_000 });
  await switchTo(page, "abhi3");
  await page.getByRole("heading", { name: /Flagged as ambiguous/ }).waitFor({ timeout: 60_000 });
  await settle(page);
  await shot("guideline-health");
  await page.goto(`${WEB}/app/rulebook`);
  await page.getByRole("tab", { name: "Compiler" }).click();
  await page.getByRole("button", { name: "Compile the sample brand book" }).click();
  await page.getByRole("heading", { name: /Review queue/ }).waitFor({ timeout: 120_000 });
  await page.getByRole("heading", { name: /Review queue/ }).scrollIntoViewIfNeeded();
  await page.evaluate(() => window.scrollBy(0, -260));
  await page.waitForTimeout(500);
  await shot("compiler");
  await page.getByRole("tab", { name: "Voice" }).click();
  await page.getByRole("heading", { name: "Hand-set targets and learned fingerprint" }).waitFor({ timeout: 60_000 });
  await page.getByRole("heading", { name: "Hand-set targets and learned fingerprint" }).scrollIntoViewIfNeeded();
  await page.evaluate(() => window.scrollBy(0, -330));
  await page.waitForTimeout(600);
  await shot("voice-fingerprint");

  // A clearance certificate from the demo history.
  const token = await page.evaluate(() => localStorage.getItem("preflight.token"));
  const reviews = await (await fetch(`${API}/api/reviews?scope=all`, { headers: { Authorization: `Bearer ${token}` } })).json();
  const approved = reviews.find((r) => r.state === "approved");
  await page.goto(`${WEB}/receipt/${approved.id}`);
  await page.getByText("Audit chain verified").waitFor({ timeout: 60_000 });
  await settle(page);
  await shot("certificate");
  console.log(`${scheme} done`);
  await context.close();
}
await browser.close();
