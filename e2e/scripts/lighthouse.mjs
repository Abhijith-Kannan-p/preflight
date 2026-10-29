// Lighthouse on every main page (mobile emulation, Lighthouse's defaults).
// Usage: CHROME_PATH=<chrome> node scripts/lighthouse.mjs <frontend URL> [out.json]
// App pages create their own demo session in the browser, as a first-time visitor's would.
// console_errors must be 0: an app page that cannot reach the API audits a loading screen.
// The 404 page is left out: Lighthouse does not audit a page served with status 404 (axe does).
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const WEB = (process.argv[2] ?? "http://localhost:3100").replace(/\/$/, "");
const OUT = process.argv[3];
const PAGES = ["/", "/app", "/app/review/new", "/app/queue", "/app/rulebook", "/app/governance", "/app/insights", "/app/evaluation", "/app/settings"];
const dir = mkdtempSync(join(tmpdir(), "lh-"));
const rows = [];
for (const path of PAGES) {
  const file = join(dir, "report.json");
  try {
    execFileSync(
      "npx",
      ["--yes", "lighthouse@12.2.1", `${WEB}${path}`, "--quiet", "--output=json", `--output-path=${file}`, "--only-categories=accessibility,best-practices,performance", '--chrome-flags=--headless=new'],
      { stdio: "ignore", shell: true },
    );
  } catch {
    // Lighthouse exits non-zero on some page errors but still writes its report.
  }
  const lh = JSON.parse(readFileSync(file, "utf8"));
  const score = (c) => Math.round((lh.categories[c]?.score ?? 0) * 100);
  const failed = Object.values(lh.audits)
    .filter((a) => a.score === 0 && lh.categories.accessibility.auditRefs.some((r) => r.id === a.id && r.weight > 0))
    .map((a) => a.id);
  rows.push({ page: path, accessibility: score("accessibility"), best_practices: score("best-practices"), performance: score("performance"), lcp_s: +(lh.audits["largest-contentful-paint"].numericValue / 1000).toFixed(1), console_errors: lh.audits["errors-in-console"].details?.items?.length ?? 0, a11y_failed: failed.join(" ") });
}
console.table(rows);
if (OUT) writeFileSync(OUT, JSON.stringify({ url: WEB, at: new Date().toISOString(), rows }, null, 1));
