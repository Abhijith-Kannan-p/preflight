import { expect, type Page, test } from "@playwright/test";

// The murmuration hero: server-rendered text and actions, a decorative canvas that paints
// after hydration, follows the theme live, stays still with reduced motion, and fits phones.

/** The canvas pixel at a point (CSS px), as [r, g, b]. */
async function pixel(page: Page, x: number, y: number) {
  return page.evaluate(([px, py]) => {
    const canvas = document.querySelector<HTMLCanvasElement>(".hero canvas");
    if (!canvas || !canvas.width) return [0, 0, 0];
    const ratio = canvas.width / canvas.getBoundingClientRect().width;
    const data = canvas.getContext("2d")!.getImageData(Math.round(px * ratio), Math.round(py * ratio), 1, 1).data;
    return [data[0], data[1], data[2]];
  }, [x, y]);
}

/** A cheap fingerprint of the canvas, to tell whether it is moving. */
async function fingerprint(page: Page) {
  return page.evaluate(() => {
    const canvas = document.querySelector<HTMLCanvasElement>(".hero canvas")!;
    return canvas.toDataURL("image/png").length + ":" + canvas.toDataURL("image/png").slice(-200);
  });
}

test("hero: text first, canvas decorative, see how it works, live theme", async ({ page }) => {
  // The headline and buttons are in the server HTML, before any script runs.
  const html = await (await page.request.get("/")).text();
  expect(html).toContain("Every claim earns its place.");
  expect(html).toContain("Open the demo desk");

  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Every claim earns its place." })).toBeVisible();
  const canvas = page.locator(".hero canvas");
  await expect(canvas).toHaveAttribute("aria-hidden", "true");
  await expect(page.locator(".hero .sr-only", { hasText: "PREFLIGHT" })).toBeAttached();

  // It animates.
  await page.waitForTimeout(1500);
  const a = await fingerprint(page);
  await page.waitForTimeout(400);
  expect(await fingerprint(page)).not.toBe(a);

  // The hawk: moving the pointer over the hero is handled without errors.
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  for (let x = 300; x < 1100; x += 80) await page.mouse.move(x, 340);

  // Theme toggle switches the preset live: the sky near the top turns from paper to dusk.
  const [lr, lg, lb] = await pixel(page, 720, 60);
  expect(lr + lg + lb).toBeGreaterThan(600);
  await page.getByRole("button", { name: /Switch to Warm Night Desk/ }).click();
  await expect.poll(async () => (await pixel(page, 720, 60)).reduce((s, v) => s + v, 0)).toBeLessThan(300);
  expect(errors).toEqual([]);

  // See how it works scrolls to the landing content and moves focus there.
  await page.getByRole("link", { name: "See how it works" }).click();
  await expect(page.locator("#overview")).toBeFocused();
  await expect(page.getByRole("heading", { name: "Every claim checked against the rulebook before it goes live." })).toBeInViewport({ timeout: 5_000 });

  // Off-screen, the loop pauses.
  await page.waitForTimeout(1200);
  const off = await fingerprint(page);
  await page.waitForTimeout(500);
  expect(await fingerprint(page)).toBe(off);
});

test("hero with reduced motion shows the formed word, still", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce", colorScheme: "dark" });
  await page.goto("/");
  await expect(page.getByRole("link", { name: "Open the demo desk" }).first()).toBeVisible();
  await page.waitForTimeout(1500);
  const a = await fingerprint(page);
  await page.waitForTimeout(700);
  expect(await fingerprint(page)).toBe(a);
  // Birds sit in the word: dark silhouettes inside the word's band, not just sky.
  const box = await page.locator(".hero > div[aria-hidden]").boundingBox();
  let dark = 0;
  for (let i = 0; i < 40; i++) {
    const [r, g, b] = await pixel(page, box!.x + box!.width * (0.1 + 0.02 * i), box!.y + box!.height / 2);
    if (r + g + b < 200) dark++;
  }
  expect(dark).toBeGreaterThan(4);
});

test("hero on a phone: word fits, buttons stack, touch does not block scrolling", async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 375, height: 812 }, hasTouch: true, isMobile: true });
  const page = await context.newPage();
  await page.goto("/");
  const demo = page.getByRole("link", { name: "Open the demo desk" }).first();
  const how = page.getByRole("link", { name: "See how it works" });
  await expect(demo).toBeInViewport();
  const [d, h] = [await demo.boundingBox(), await how.boundingBox()];
  expect(h!.y).toBeGreaterThan(d!.y + d!.height - 1); // stacked
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
  const touchAction = await page.locator(".hero").evaluate((el) => getComputedStyle(el).touchAction);
  expect(touchAction).not.toBe("none");
  await page.locator(".hero").tap({ position: { x: 180, y: 300 } });
  await page.mouse.wheel(0, 900);
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(100);
  await context.close();
});
