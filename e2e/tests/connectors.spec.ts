import { expect, type Page, test } from "@playwright/test";

// Connectors on the landing specimen (the same Proof Desk as a review, with static data):
// one per visible note, each ending on its note's number badge after expanding, filtering and
// resizing; the active one drawn at full strength; none below 1024 px.

/** Each connector's end against its note's badge centre, in px (desk coordinates). */
async function misalignment(page: Page) {
  return page.evaluate(() => {
    const svg = document.querySelector<SVGSVGElement>("svg[data-connectors]");
    if (!svg) return { count: 0, notes: 0, worst: Infinity };
    const origin = svg.getBoundingClientRect();
    const groups = [...svg.querySelectorAll<SVGGElement>("[data-connector]")];
    let worst = 0;
    for (const g of groups) {
      const id = g.dataset.connector!;
      const d = g.querySelector("path")!.getAttribute("d")!;
      // Every path ends "V <note y> H <note x>".
      const [y, x] = d.match(/V (-?[\d.]+) H (-?[\d.]+)$/)!.slice(1).map(Number);
      const badge = document.querySelector(`[data-note="${id}"] [data-badge]`)!.getBoundingClientRect();
      worst = Math.max(worst, Math.abs(badge.left - origin.left - x), Math.abs(badge.top + badge.height / 2 - origin.top - y));
    }
    return { count: groups.length, notes: document.querySelectorAll("[data-note]").length, worst };
  });
}

async function settle(page: Page) {
  await page.waitForTimeout(450); // notes move with a 200 ms transition; connectors follow
}

test("every note is connected to its mark, and stays connected", async ({ page }) => {
  await page.goto("/");
  const sheet = page.getByRole("region", { name: "Proof sheet" }).first();
  await sheet.scrollIntoViewIfNeeded();
  await settle(page);

  let m = await misalignment(page);
  expect(m.count).toBeGreaterThan(3);
  expect(m.count).toBe(m.notes);
  expect(m.worst).toBeLessThanOrEqual(1.5);

  // The active note: full strength and 2 px; the rest about a third, 1 px.
  const third = page.locator("[data-note]").nth(2);
  await third.hover();
  const id = await third.getAttribute("data-note");
  const line = page.locator(`[data-connector="${id}"]`);
  await expect(line).toHaveClass(/opacity-100/);
  await expect(line.locator("path")).toHaveAttribute("stroke-width", "2");
  await expect(page.locator("[data-connector]").filter({ hasNot: page.locator(`[data-connector="${id}"]`) }).first()).toHaveClass(/opacity-\[0\.35\]/);

  // Expanding a note pushes the notes below it down; their lines follow.
  await page.locator("[data-note]").first().click();
  await settle(page);
  m = await misalignment(page);
  expect(m.count).toBe(m.notes);
  expect(m.worst).toBeLessThanOrEqual(1.5);

  // Filtering out a severity removes its notes and their lines.
  const summary = page.getByRole("region", { name: "Proof summary" }).first();
  const minor = summary.getByRole("button", { name: /minor/i });
  await minor.click();
  await settle(page);
  m = await misalignment(page);
  expect(m.count).toBe(m.notes);
  expect(await page.locator("[data-connector]").count()).toBeLessThan(6);
  expect(m.worst).toBeLessThanOrEqual(1.5);
  await minor.click();
  await settle(page);

  // Resizing keeps them aligned; below 1024 px the notes go inline, without lines.
  await page.setViewportSize({ width: 1100, height: 900 });
  await settle(page);
  m = await misalignment(page);
  expect(m.count).toBe(m.notes);
  expect(m.worst).toBeLessThanOrEqual(1.5);
  await page.setViewportSize({ width: 900, height: 900 });
  await settle(page);
  await expect(page.locator("svg[data-connectors]")).toHaveCount(0);
});
