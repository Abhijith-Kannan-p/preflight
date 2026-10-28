// Times visual reviews against an API (e.g. a 512 MB / 0.1 CPU container or Render).
// Usage: node scripts/visual-timing.mjs <API URL>
const API = process.argv[2] ?? "http://127.0.0.1:8000";
const s = await (await fetch(`${API}/api/sandbox/session`, { method: "POST", headers: { "content-type": "application/json" }, body: "{}" })).json();
const auth = { authorization: `Bearer ${s.token}` };
const samples = (process.argv[3] ?? "sample_linkedin,sample_festive_banner,sample_scanned_flyer,sample_stretched_logo,sample_clean_visual,sample_email_images,sample_clean").split(",");
const rows = [];
for (const sample of samples) {
  const form = new FormData();
  form.set("channel", "linkedin");
  form.set("sample_id", sample);
  form.set("title", `${sample} ${Date.now()}`);
  const t0 = Date.now();
  const { id } = await (await fetch(`${API}/api/reviews`, { method: "POST", body: form, headers: auth })).json();
  let r;
  for (;;) {
    r = await (await fetch(`${API}/api/reviews/${id}`, { headers: auth })).json();
    if (r.revision.review_status !== "pending") break;
    await new Promise((x) => setTimeout(x, 1000));
  }
  const steps = Object.fromEntries((r.revision.report.checkers ?? []).map((c) => [c.name, c.ms]));
  rows.push({ sample, status: r.revision.review_status, total_s: (Date.now() - t0) / 1000, ocr_s: (steps.ocr ?? 0) / 1000, cached: Boolean(r.revision.report.cached_from), rules: [...new Set(r.findings.map((f) => f.rule.id))].join(" ") });
}
console.table(rows);
