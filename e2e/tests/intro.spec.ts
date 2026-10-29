import { expect, test, type Page } from "@playwright/test";

// The landing intro: driven by the page's own scroll, never traps the page, can be skipped,
// replays in reverse, is remembered for the session, and is still for reduced motion.

const landingTop = (page: Page) => page.evaluate(() => document.getElementById("landing")!.getBoundingClientRect().top);
const hero = (page: Page) => page.getByRole("heading", { name: /Every claim checked against the rulebook/ });

test("wheel and keys drive the intro into the landing page, and back", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Every claim, cleared." })).toBeVisible();
  // Wheel through most of the tunnel (1.75 viewports of travel) and stop: the page glides on
  // and settles exactly on the landing section.
  const travel = await page.evaluate(() => document.querySelector<HTMLElement>(".intro-stage")!.offsetHeight - window.innerHeight);
  for (let i = 0; i < 6; i++) {
    await page.mouse.wheel(0, Math.round((travel * 0.86) / 6));
    await page.waitForTimeout(60);
  }
  await expect.poll(async () => Math.abs(await landingTop(page)), { timeout: 10_000 }).toBeLessThanOrEqual(2);
  await expect(hero(page)).toBeInViewport();
  // Normal scrolling continues on the landing page.
  await page.mouse.wheel(0, 600);
  await expect.poll(() => landingTop(page)).toBeLessThan(-300);
  // Scrolling back up past the landing top re-enters the intro in reverse.
  await page.mouse.wheel(0, -4000);
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeLessThan(50);
  await expect(page.getByRole("heading", { name: "Every claim, cleared." })).toBeInViewport();

  // Keyboard: PageDown and Space move through it the same way.
  await page.locator("body").click({ position: { x: 5, y: 300 } });
  for (const key of ["PageDown", "PageDown", "Space", "PageDown"]) {
    await page.keyboard.press(key);
    await page.waitForTimeout(250);
  }
  await expect.poll(() => landingTop(page), { timeout: 10_000 }).toBeLessThanOrEqual(2);
});

test("skip, session memory and replay", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Skip intro" }).first().click();
  await expect(hero(page)).toBeInViewport();
  // The rest of the session starts at the landing page, with a way back to the intro.
  await page.reload();
  await expect(page.getByRole("heading", { name: "Every claim, cleared." })).toBeHidden();
  await expect(hero(page)).toBeInViewport();
  await page.getByRole("button", { name: "Replay intro" }).click();
  await expect(page.getByRole("heading", { name: "Every claim, cleared." })).toBeInViewport();
  // The app itself is never blocked by the intro.
  await page.goto("/app");
  await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible({ timeout: 60_000 });
});

test("reduced motion shows a still intro with Continue", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Every claim, cleared." })).toBeVisible();
  const height = await page.evaluate(() => document.querySelector(".intro-stage")!.getBoundingClientRect().height);
  expect(height, "no tunnel travel").toBeLessThanOrEqual(await page.evaluate(() => window.innerHeight + 2));
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(hero(page)).toBeInViewport();
});

test("phone: touch drag moves through the intro, which fits and can be skipped", async ({ browser }) => {
  const page = await (await browser.newContext({ viewport: { width: 375, height: 812 }, hasTouch: true, isMobile: true })).newPage();
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Every claim, cleared." })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  // Touch drag is the browser's own scrolling: nothing on the stage may block it. (Headless
  // Chrome's synthetic touch gestures do not scroll even a plain page, so the gesture below
  // uses the default source; touch on a real phone is in the manual checklist.)
  const blocked = await page.evaluate(() => [...document.querySelectorAll(".intro-stage, .intro-stage *")].some((el) => getComputedStyle(el).touchAction === "none"));
  expect(blocked, "no touch-action: none on the intro").toBe(false);
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Input.synthesizeScrollGesture", { x: 187, y: 600, yDistance: -500 });
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(200);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.getByRole("button", { name: "Skip intro" }).first().click();
  await expect(hero(page)).toBeInViewport();
});
