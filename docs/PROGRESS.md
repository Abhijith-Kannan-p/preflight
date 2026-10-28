# Round 3 progress

Updated after every commit checkpoint. Build order follows section 13 of the Round 3 spec.

## Done
- 1. Audit and plan (2026-10-28). Key findings recorded below and in `OPEN_QUESTIONS.md`.
- 2. Proof Desk design system (2026-10-28): tokens, fonts, Proof Sheet with margin notes and
  leader lines (inline below 1024px), source drawer for rule/fact tags, Preflight Checklist
  with live claims over SSE, instrument Brand Score dial, Clearance Stamp, Clearance
  Certificate (boarding pass, QR, A4 print, matching PDF), departures-board lists, landing
  rebuilt around a Proof Sheet specimen, restyled splash and header. Checked at 1440/768/375
  with no horizontal scroll; backend 113 tests, e2e 5/5 locally, production build green.

- 3. Per-visitor sandboxes, keep-warm, robustness foundations (2026-10-28):
  - Sandboxes: template cloned in the database (about 80–110 ms locally), personas copied
    with suffixed ids, per-workspace audit chains, first-party httpOnly cookie through a
    Next.js rewrite, in-place reset, 24 h idle expiry with a sweeper, review cache keyed by
    a context fingerprint so identical sandboxes share results safely.
  - Robustness: review job queue (positions, reattach after restart, 120 s budget),
    `Idempotency-Key` middleware plus no-op repeated decisions, client timeouts (45 s),
    SSE reconnect with backoff and a 60 s stall state, friendly JSON 500s with a reference,
    styled 404/500 pages and error boundaries, wrong-role hints, keep-warm workflow.
  - Tests: backend 143 (new: sandboxes 8, queue 2, idempotency 6, bad input 14), e2e 6 including
    a two-browser isolation test; five concurrent reviews all completed locally.

- 4. Improvement 1: Visual and accessibility review (2026-10-28): intake for images, scans
  and HTML; RapidOCR with layout; VIS-01/02/03 and ACC-01/02/03; Visual Review desk; palette
  editor; five samples and a PayWise logo; 100-asset labelled set and evaluation tab
  (precision 1.00, recall 0.99, OCR words 98.3%). Measured at 512 MB / 0.1 CPU: server peak
  437 MiB, OCR 6.8 s per banner (target 6 s missed on 0.1 CPU; 1.3 s on a normal CPU).
  Tests: backend 185, e2e 7.

- 5. Improvement 2: Governance intelligence (2026-10-28): richer seeded history (36 entries,
  disputes with reasons, overrides, DSC-01 reworded to v2, recurring mistakes) generated in
  deterministic mode in ~9 s; Guideline Health, Stale-Content Radar (notifications on every
  fact change), Creator Coach (Governance page + New review panel). Found and fixed: offline
  tone heuristic flagged two-thirds of drafts (now waits in Needs a human look); a role
  switch during the first session load was dropped. Tests: backend 190, e2e 8.

- 6. Improvement 3: Brand Autopilot (2026-10-29): Rulebook Compiler (20-page fictional PayWise
  Brand Book, structured extraction + Gemini for prose, schema check, comparison with the
  rulebook, review queue with the source excerpt, SSE stages, structured-only fallback with a
  banner) and Voice Fingerprint (learned from approved content, radar against hand-set targets,
  "Adopt as targets" as a new voice-profile version, dispute rate per version and a labelled
  replay). Compiler on 51 hand labels: recall 94%, precision 100%, 100% acceptable without
  edits (mean of 3 Gemini runs); 82% / 100% / 98% with structured extraction only. Fingerprint
  replay: tone flags 24 → 9 of 36 drafts, 6 of 6 disputed drafts no longer flagged. Found and
  fixed: a wrapped table cell kept its line break; one malformed LLM item sank a whole answer;
  an SSE effect reopened the stream on every render. Tests: backend 200, e2e 9.

- 7. Round 2 loose ends (2026-10-29): webhooks for `submission.approved`, `review.published`
  and `finding.critical`, 3 attempts with 2 s / 4 s backoff, per-attempt delivery log, Resend
  and per-webhook event choice; notifications pushed over SSE (polling only while the stream
  is down); 20 labelled full drafts (precision 0.92, recall 0.89, 15/20 exactly right, 7/7
  clean drafts pass); Claim Ledger `unsupported` precision 0.84 → **0.94** (target 0.90) on
  the 150-claim set, **0.67** on 27 held-out claims written afterwards. Found and fixed: a
  local template seeded without the embedder had no fact vectors (now back-filled at boot);
  a low-confidence tone finding hid a confident punctuation finding; claims written as "we"
  were not read as PayWise; production would have kept showing the old evaluation run.
  Tests: backend 210, e2e 11.

## In progress
- 8. Hardening and testing

## Next
- 9. Documentation and handover

## Blockers
- None.

## Audit notes (2026-10-28)
- Live: frontend on Vercel, backend healthy on Render (`preflight-api-nauz.onrender.com`), CI green.
- Sandboxes need a migration: `Fact.id`, `ChannelProfile.id` and `SampleDraft.id` are global
  primary keys; 37 code paths use a single `WORKSPACE_ID`.
- Cross-site httpOnly cookies are blocked in incognito; the API will be proxied through Vercel
  rewrites so the sandbox cookie is first-party.
- RapidOCR on ONNX Runtime measured in a Render-like container (0.1 CPU): 1200×630 banner read
  correctly in 5.4–6.5 s (0.4–0.5 s on 1 CPU), +~100 MiB steady, +~130 MiB transient. It cannot
  share memory with the NLI model under the 450 MiB budget, so heavy models will be swapped.
