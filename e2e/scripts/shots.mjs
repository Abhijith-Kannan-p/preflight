// Screenshots of the main pages in both themes, for design review and the README.
// Usage: node scripts/shots.mjs <frontend URL> <out dir> [width] [pages...]
// Pages are paths; a path may end with "#role" to switch to that demo user first.
import { chromium } from "playwright";

const [WEB = "http://localhost:3000", OUT = ".", WIDTH = "1440", ...rest] = process.argv.slice(2);
const width = Number(WIDTH);
const pages = rest.length ? rest : ["/app", "/app/review/new", "/app/rulebook#abhi3", "/app/governance#abhi3", "/app/evaluation", "/app/settings#abhi5"];
const browser = await chromium.launch();
for (const scheme of ["dark", "light"]) {
  const context = await browser.newContext({ viewport: { width, height: 900 }, colorScheme: scheme });
  const page = await context.newPage();
  await page.addInitScript(() => localStorage.setItem("preflight.tour.done", "1"));
  for (const target of pages) {
    const [path, role] = target.split("#");
    await page.goto(`${WEB}${path}`);
    await page.locator('[data-tour="role-switcher"] button').first().waitFor({ timeout: 90_000 });
    if (role) {
      await page.locator('[data-tour="role-switcher"] button').first().click();
      await page.getByRole("option", { name: new RegExp(`^${role}`) }).click();
      await page.waitForTimeout(1200);
    }
    await page.waitForLoadState("networkidle").catch(() => {});
    await page.waitForTimeout(800);
    const name = `${scheme}-${width}-${path.replace(/[/?=&]+/g, "_").replace(/^_/, "") || "root"}`;
    await page.screenshot({ path: `${OUT}/${name}.png` });
    console.log(name);
  }
  await context.close();
}
await browser.close();
