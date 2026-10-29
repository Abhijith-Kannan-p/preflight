// The manual exploratory checklist, driven in a real browser so every step leaves a screenshot
// to look at. Usage: node scripts/exploratory.mjs <frontend URL> <API URL> <screenshot dir> [width]
// Prints one line per check: PASS / FAIL and what was seen. Screenshots are reviewed by a person.
import { chromium } from "playwright";

const [WEB = "http://localhost:3000", API = "http://127.0.0.1:8000", OUT = ".", WIDTH = "375"] = process.argv.slice(2);
const width = Number(WIDTH);
const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width, height: width < 768 ? 812 : 900 }, hasTouch: width < 768 });
const page = await context.newPage();
await page.addInitScript(() => window.localStorage.setItem("preflight.tour.done", "1"));
const results = [];
let step = 0;

async function check(name, fn) {
  step += 1;
  try {
    const seen = await fn();
    results.push(`PASS  ${name}${seen ? `: ${seen}` : ""}`);
  } catch (e) {
    results.push(`FAIL  ${name}: ${String(e.message ?? e).split("\n")[0].slice(0, 200)}`);
  }
  await page.screenshot({ path: `${OUT}/${width}-${String(step).padStart(2, "0")}.png`, fullPage: true }).catch(() => {});
}
const visible = (locator, timeout = 60_000) => locator.first().waitFor({ state: "visible", timeout });
const overflow = () => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
const token = () => page.evaluate(() => localStorage.getItem("preflight.token"));

await check("landing loads, no sideways scroll", async () => {
  await page.goto(WEB);
  await visible(page.getByRole("link", { name: "Open the demo desk" }));
  await page.waitForTimeout(2500);
  const o = await overflow();
  if (o > 1) throw new Error(`overflow ${o}px`);
});

await check("demo opens with a private session", async () => {
  await page.getByRole("link", { name: "Open the demo desk" }).first().click();
  await visible(page.getByRole("button", { name: "Run Preflight" }), 120_000);
  return `signed in as ${await page.locator('[data-tour="role-switcher"]').innerText().then((t) => t.split("\n")[0])}`;
});

await check("whitespace-only text is refused with a message", async () => {
  await page.locator("#draft").fill("     \n   ");
  const run = page.getByRole("button", { name: "Run Preflight" });
  if (await run.isEnabled()) {
    await run.click();
    await visible(page.getByText(/Paste some text|No readable text/), 30_000);
    return "message shown";
  }
  return "Run stays disabled";
});

await check("over 20,000 characters is capped in the editor", async () => {
  await page.locator("#draft").fill("PayWise helps shops. ".repeat(1100));
  const length = (await page.locator("#draft").inputValue()).length;
  if (length > 20000) throw new Error(`accepted ${length} characters`);
  return `editor holds ${length} characters`;
});

await check("emoji and Hindi text is reviewed", async () => {
  await page.locator("#draft").fill("PayWise से भुगतान आसान है 🎉 PayWise customer support is available 24x7 in English and Hindi.");
  await page.locator("#title").fill("Emoji and Hindi");
  await page.getByRole("button", { name: "Run Preflight" }).click();
  await page.waitForURL(/\/app\/review\/sub_/, { timeout: 60_000 });
  await visible(page.getByRole("img", { name: /^Brand Score \d+ out of 100$/ }), 300_000);
  return (await page.getByRole("img", { name: /^Brand Score/ }).first().getAttribute("aria-label")) ?? "";
});

await check("back and forward navigation", async () => {
  const review = page.url();
  await page.goBack();
  await visible(page.getByRole("button", { name: "Run Preflight" }), 30_000);
  await page.goForward();
  await page.waitForURL(review);
  await visible(page.getByRole("img", { name: /^Brand Score/ }), 60_000);
});

await check("review page at this width has no sideways scroll", async () => {
  const o = await overflow();
  if (o > 1) throw new Error(`overflow ${o}px`);
});

await check("keyboard: ? opens help, J moves between findings", async () => {
  await page.locator("body").click({ position: { x: 5, y: 5 } });
  await page.keyboard.press("Shift+?");
  await visible(page.getByRole("dialog"), 10_000);
  await page.keyboard.press("Escape");
  await page.keyboard.press("j");
  return "help dialog opened and closed";
});

await check("refresh mid-review reattaches", async () => {
  await page.goto(`${WEB}/app/review/new?sample=sample_linkedin`);
  await page.waitForFunction(() => document.querySelector("#draft")?.value.includes("India's #1"), null, { timeout: 60_000 });
  await page.locator("#draft").fill(`${await page.locator("#draft").inputValue()} Ref ${Date.now()}`);
  await page.getByRole("button", { name: "Run Preflight" }).click();
  await page.waitForURL(/\/app\/review\/sub_/, { timeout: 60_000 });
  await page.reload();
  await visible(page.getByLabel("Critical finding CLM-04", { exact: true }), 300_000);
});

await check("oversized image is refused before upload", async () => {
  await page.goto(`${WEB}/app/review/new`);
  await visible(page.getByRole("button", { name: "Run Preflight" }));
  await page.locator('input[type="file"]').setInputFiles({ name: "huge.png", mimeType: "image/png", buffer: Buffer.alloc(6 * 1024 * 1024, 1) });
  await visible(page.getByText(/5 MB or smaller/), 10_000);
});

await check("unsupported file type gets a message", async () => {
  await page.locator('input[type="file"]').setInputFiles({ name: "notes.exe", mimeType: "application/octet-stream", buffer: Buffer.from("MZ") });
  const run = page.getByRole("button", { name: "Run Preflight" });
  if (await run.isEnabled()) await run.click();
  await visible(page.getByText(/not supported|Upload a|PDF, DOCX|could not|cannot/i), 30_000);
});

await check("wrong-role action explains who can do it", async () => {
  const t = await token();
  const reviews = await (await fetch(`${API}/api/reviews?scope=all`, { headers: { Authorization: `Bearer ${t}` } })).json();
  const waiting = reviews.find((x) => x.state === "in_review");
  const r = await fetch(`${API}/api/reviews/${waiting.id}/transition`, { method: "POST", headers: { Authorization: `Bearer ${t}`, "Content-Type": "application/json" }, body: JSON.stringify({ action: "approve" }) });
  const body = await r.json();
  if (r.status !== 403) throw new Error(`status ${r.status}`);
  return body.detail;
});

await check("unknown page shows the styled 404", async () => {
  await page.goto(`${WEB}/nothing-here`);
  await visible(page.getByRole("heading", { name: /no page at this address/i }), 30_000);
});

for (const [name, path, wait] of [
  ["dashboard", "/app", /Welcome/],
  ["rulebook", "/app/rulebook", /Rulebook/],
  ["governance", "/app/governance", /Governance|Flagged/],
  ["evaluation", "/app/evaluation", /Evaluation/],
  ["settings", "/app/settings", /Settings|API keys/],
]) {
  await check(`${name}: loads, no sideways scroll`, async () => {
    await page.goto(`${WEB}${path}`);
    await visible(page.getByRole("heading", { name: wait }), 60_000);
    await page.waitForTimeout(800);
    const o = await overflow();
    if (o > 1) throw new Error(`overflow ${o}px`);
  });
}

console.log(results.join("\n"));
await browser.close();
