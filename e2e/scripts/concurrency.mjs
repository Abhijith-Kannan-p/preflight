// Load check: five visitors (five sandboxes) start different reviews at the same moment and
// every one must complete. Usage: node scripts/concurrency.mjs <frontend URL> <API URL>
const WEB = process.argv[2] ?? "http://localhost:3000";
const API = process.argv[3] ?? "http://127.0.0.1:8000";
async function visitor(n) {
  const s = await (await fetch(`${WEB}/api/sandbox/session`, { method: "POST", headers: { "content-type": "application/json" }, body: "{}" })).json();
  const auth = { authorization: `Bearer ${s.token}` };
  const form = new FormData();
  form.set("channel", "linkedin");
  form.set("content", `Visitor ${n} at ${Date.now()}: PayWise settles in under 5 seconds and is 100% secure! Download today.`);
  const t0 = Date.now();
  const { id } = await (await fetch(`${API}/api/reviews`, { method: "POST", body: form, headers: auth })).json();
  let maxQueue = 0, r;
  for (;;) {
    r = await (await fetch(`${API}/api/reviews/${id}`, { headers: auth })).json();
    maxQueue = Math.max(maxQueue, r.queue_position ?? 0);
    if (r.revision.review_status !== "pending") break;
    await new Promise((x) => setTimeout(x, 500));
  }
  return { n, status: r.revision.review_status, seconds: (Date.now() - t0) / 1000, maxQueue, findings: r.findings.length };
}
const results = await Promise.all([1, 2, 3, 4, 5].map(visitor));
console.table(results);
