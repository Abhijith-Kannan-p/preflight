# Completed features

Every item in the Round 1 plan's "MUST · Round 2" column, with its status and where to see
it. Live app: https://preflight-eight-smoky.vercel.app. Demo users are switched from the
top-right role switcher (abhi1 Creator, abhi2 Reviewer, abhi3 Brand Manager, abhi4 Approver,
abhi5 Admin).

| # | Round 1 feature | Status | Where to see it |
|---|---|---|---|
| 1 | **Brand Knowledge Base**: rules, approved facts (validity, versioning), terminology, channel profiles, confidential terms; CRUD + CSV import/export | ✅ Done | **Rulebook**. As abhi3: New rule, edit (creates a new version; history icon), Supersede a fact, Import/Export CSV |
| 2 | **Multi-format intake**: text/Markdown, DOCX, PDF into blocks with offsets | ✅ Done | **New review**: paste, drop a file, or the DOCX and PDF sample drafts |
| 3 | **Language and terminology checks**: product names and capitalisation, banned/discouraged phrases, required disclaimers, channel limits, readability | ✅ Done | Any review: TRM-02, TRM-05, DSC-01/02, CHN-01/02/03, RDB-01, TON-03 findings |
| 4 | **Claim Ledger**: detect → retrieve → NLI → exact quote → verdict (supported, outdated, contradicted, unsupported, needs_review) | ✅ Done | Review → **Claim Ledger** tab, with "How this verdict was reached" on every row |
| 5 | **Tone check** against the five-trait voice profile, with deterministic fallback | ✅ Done | TON-01 findings; review → **AI disclosure** tab shows the tone profile vs targets |
| 6 | **Explainable findings** (issue, reference, severity, confidence, suggestion, drift) | ✅ Done | Every finding card |
| 7 | **Intent-preserving suggestions** with drift; Accept / Edit / Dispute (reason) / Escalate; never auto-applied | ✅ Done | Finding cards; accepted changes apply only on **Re-check** |
| 8 | **Review workflow**: roles, state machine, comments, revision history with diff, re-check, approval gate, hash-chained audit log | ✅ Done | Review → Revisions and Comments tabs; Submit is disabled while criticals are open; Settings → Verify audit chain |
| 9 | **Review Receipt**: one-page record, PDF and shareable page | ✅ Done | Approved review → **View Review Receipt** → Download PDF / Copy share link |
| 10 | **Brand Score** gauge (0–100) | ✅ Done | Review workspace; tooltip explains the formula |
| 11 | **Governance insights**: findings by type, top violated rules, dispute rate per rule, trend | ✅ Done | **Insights** (abhi2, abhi3, abhi4 or abhi5); also findings per author |
| 12 | **Integrations**: public REST API with keys, OpenAPI docs, outgoing webhook on approval (Slack option) | ✅ Done | Settings (abhi5) → API keys (curl example), Webhooks (Send test event, delivery log); `/docs`; `examples/cms_hook.py` |
| 13 | **Privacy and AI transparency**: masking before LLM calls, "AI used in this review" panel | ✅ Done | Review → AI disclosure tab; Rulebook → Confidential terms; Settings → masking switch; receipt footer |
| 14 | **Evaluation page**: labelled test set, live precision/recall, confusion matrix | ✅ Done | **Evaluation**: 150 labelled claims, per-verdict metrics, confusion matrix, failure cases, Run button |
| 15 | **Zero-setup demo**: PayWise brand, samples, role switcher, guided tour | ✅ Done | Landing → Try the live demo; four sample drafts; generated demo history; 5-step tour (re-open with "?") |
| 16 | **Deployed** frontend and backend with health check, plus CI | ✅ Done | Vercel + Render (free, 512 MB); `/health`; "Waking up the engine…" screen; GitHub Actions badge |

## Also built

- **Approval queue** page for approvers, and a dashboard with state chips and average score.
- **Notifications** bell: submitted, changes requested, approved, escalated, commented.
- **Keyboard shortcuts** on the review page: J/K move, A accept, E edit, D dispute, ? help.
- **Live progress over SSE**: each checker ticks green as it finishes; deterministic findings
  arrive in under two seconds.
- **Graceful degradation**: if Gemini times out or fails three times, a circuit breaker
  switches to deterministic mode and the review shows "AI checks temporarily limited".
- **Result caching** by content hash and a fingerprint of the rulebook, facts, channel and date.
- **Admin "Reset demo data"**, which also regenerates the fictional review history.

## Added in Round 3 (so far)

| Feature | Where to see it |
|---|---|
| **Proof Desk design**: the draft as a proof sheet with proof marks and margin notes joined by leader lines (inline below 1024 px); rule and fact tags open their source; preflight checklist with live claims; instrument Brand Score dial; "Next step" hint | Any review |
| **Clearance stamp and certificate**: "CLEARED FOR PUBLICATION" (approver, time, audit hash) and "OVERRIDE NOTED"; boarding-pass certificate with QR code, A4 print and matching PDF | Approve a review, then View Review Receipt |
| **Private demo workspace per visitor**: each browser gets its own copy of PayWise (rules, facts, personas, history, audit chain), kept in an httpOnly cookie; reset touches only that copy; idle copies are deleted after 24 h | Role switcher → "Reset my demo workspace"; open the app in two browsers |
| **Review queue**: reviews are server-side jobs on a small worker pool; waiting reviews show their queue position; reloading the page reattaches to the running job | Start several reviews at once |
| **No endless spinners**: every request gives up after 45 s with a clear message; a review is stopped after 2 minutes with a "Re-check" prompt; a stalled live stream is reported after 60 s | Review page |
| **Double actions are safe**: `Idempotency-Key` on every write; repeated accepts, approvals or Run presses apply once | API docs; double-click anything |
| **Clear errors**: empty, oversized, corrupt, password-protected, renamed-binary and unsupported uploads each get a specific message; styled 404 and error pages; wrong-role actions explain which role can do it | Try a 0-byte .pdf; open a review link from another browser |
| **Keep-warm**: a scheduled GitHub Action pings `/health` every 10 minutes so visitors do not meet a sleeping backend | `.github/workflows/keep-warm.yml` |
| **Improvement 2: Governance intelligence**: Guideline Health (ambiguity score, grouped dispute reasons, LLM rewording published as a new rule version, before/after per version), Stale-Content Radar (fact-dependency index, notifications on every fact change, "Simulate fact update on F-087", Re-check now), Creator Coach (repeat-mistake rate, trend, tips on New review) | Governance (top menu) as abhi3; New review shows your coach |
| **Improvement 3: Brand Autopilot**: Rulebook Compiler (PDF or DOCX brand book → typed rule candidates with page and excerpt, compared with the rulebook as new / update / already there; accept, edit or reject; accepted rules become cited rule versions, audit-logged) and Voice Fingerprint (tone learned from approved items, radar and table against hand-set targets, adopt as a new voice-profile version, tone-dispute rate per version) | Rulebook → Compiler and Voice as abhi3; Evaluation → Rulebook Compiler |
| **Improvement 1: Visual and accessibility review**: images, scanned PDFs and HTML emails; OCR text checked like any draft; brand palette (CIEDE2000), WCAG 2.2 contrast, logo distortion and clear space, alt text; overlay boxes, palette strip, contrast table; upload a corrected version | New review → the five visual samples; Rulebook → Palette; Evaluation → Visual review (precision 1.00 on 100 labelled assets) |

## Known limitations

- Claim Ledger `unsupported` precision is 0.85 against a 0.90 target. Most misses are vague
  claims ("trusted by millions") that we labelled `needs_review`; in the app they land in the
  "Needs a human look" group and cost no points.
- Two retrieval-similarity thresholds were calibrated on the same labelled set we report on;
  there is no held-out split yet.
- Visual review on Render's 0.1 CPU: OCR takes about 7 s per image (11 s per scanned page) and a
  whole visual review 25–30 s; under 2 s on a normal CPU. The visual evaluation set is
  synthetic, so real photographs and unusual fonts will score lower than its 1.00 precision.
- The Rulebook Compiler is evaluated on one brand book that we wrote and labelled ourselves;
  real brand books with complex layouts (multi-column pages, images of tables) will do worse.
  Without the LLM it extracts tables, lists, limits and quoted phrases only.
- The demo history's tone scores come from the offline heuristic, so the Voice Fingerprint
  shown on first open is an estimate (labelled in the app). Tone-dispute rate after adoption
  fills in only as new drafts are reviewed.
- Demo authentication is a role switcher with signed tokens, not real accounts.
- On Render's free plan the backend sleeps after 15 idle minutes. The keep-warm workflow pings
  it every 10 minutes; GitHub can delay scheduled runs, so a cold start is still possible. Then
  the first visit takes about a minute, and the first review loads the models (10–20 s extra). With 0.1
  CPU a full review takes roughly 30–40 s; deterministic findings still appear first.
