import { writeFileSync } from "node:fs";

import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { apiGet, switchTo } from "./helpers";

// Accessibility and layout on every main page at phone, tablet and desktop widths:
// - axe (WCAG 2.0/2.1/2.2 A and AA rules): no serious or critical violations;
// - no horizontal page scroll.
// Set E2E_A11Y_REPORT to a file path to write every result (including minor issues) as JSON.

const WIDTHS = [375, 768, 1440];

interface ReviewItem {
  id: string;
  state: string;
}

async function pages(page: Page): Promise<{ name: string; path: string; ready: () => Promise<void>; as?: string }[]> {
  const reviews = await apiGet<ReviewItem[]>(page, "/api/reviews?scope=all");
  const approved = reviews.find((r) => r.state === "approved") ?? reviews[0];
  const heading = (name: RegExp | string) => async () => {
    await expect(page.getByRole("heading", { name }).first()).toBeVisible({ timeout: 60_000 });
  };
  return [
    { name: "landing", path: "/", ready: async () => { await expect(page.getByRole("link", { name: "Open the demo desk" }).first()).toBeVisible(); await page.waitForTimeout(2300); } },
    { name: "dashboard", path: "/app", ready: heading(/Welcome/) },
    { name: "new review", path: "/app/review/new", ready: async () => { await expect(page.getByRole("button", { name: "Run Preflight" })).toBeVisible({ timeout: 60_000 }); } },
    { name: "review", path: `/app/review/${approved.id}`, ready: async () => { await expect(page.getByRole("img", { name: /^Brand Score/ }).first()).toBeVisible({ timeout: 60_000 }); } },
    { name: "queue", path: "/app/queue", ready: heading("Queue") },
    { name: "rulebook", path: "/app/rulebook", ready: heading("Rulebook") },
    { name: "governance", path: "/app/governance", ready: heading(/Flagged as ambiguous|Governance/) },
    { name: "insights", path: "/app/insights", ready: async () => { await expect(page.getByText("Brand Score over time")).toBeVisible({ timeout: 60_000 }); } },
    { name: "evaluation", path: "/app/evaluation", ready: async () => { await expect(page.getByText("Macro recall")).toBeVisible({ timeout: 60_000 }); } },
    { name: "settings", path: "/app/settings", ready: heading("Outgoing webhooks"), as: "abhi5" },
    { name: "receipt", path: `/receipt/${approved.id}`, ready: async () => { await expect(page.getByText(/Audit chain/).first()).toBeVisible({ timeout: 60_000 }); } },
    { name: "not found", path: "/no-such-page", ready: heading(/no page at this address/i) },
  ];
}

const results: Record<string, unknown>[] = [];

for (const width of WIDTHS) {
  test(`a11y and layout at ${width} px`, async ({ page }) => {
    test.setTimeout(600_000);
    await page.setViewportSize({ width, height: width < 768 ? 812 : 900 });
    await page.addInitScript(() => window.localStorage.setItem("preflight.tour.done", "1"));
    // abhi3 (Brand Manager) can open every page; settings are the admin's.
    await page.goto("/app/settings");
    await switchTo(page, "abhi3");
    const problems: string[] = [];
    for (const target of await pages(page)) {
      await page.goto(target.path);
      if (target.as) {
        await switchTo(page, target.as);
        await page.goto(target.path);
      }
      await target.ready();
      // Pages fade in: measuring colours mid-animation reports blended, wrong contrasts.
      await page.waitForFunction(() =>
        document.getAnimations().every((a) => a.playState !== "running" || a.effect?.getTiming().iterations === Infinity),
      );
      const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
      const serious = axe.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      results.push({
        width,
        page: target.name,
        violations: axe.violations.map((v) => ({ id: v.id, impact: v.impact, nodes: v.nodes.length, sample: v.nodes.slice(0, 4).map((n) => ({ target: n.target, html: n.html.slice(0, 160), why: n.any[0]?.message })) })),
        overflow_px: overflow,
      });
      for (const v of serious) problems.push(`${width}px ${target.name}: ${v.impact} ${v.id} (${v.nodes.length}) e.g. ${JSON.stringify(v.nodes[0]?.target)}`);
      if (overflow > 1) problems.push(`${width}px ${target.name}: page scrolls sideways by ${overflow}px`);
      if (process.env.E2E_A11Y_REPORT) writeFileSync(process.env.E2E_A11Y_REPORT, JSON.stringify(results, null, 1));
    }
    expect(problems, problems.join("\n")).toEqual([]);
  });
}
