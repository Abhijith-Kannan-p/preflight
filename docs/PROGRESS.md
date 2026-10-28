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

## In progress
- 4. Improvement 1: Visual and accessibility review

## Next
- 5. Improvement 2: Governance intelligence
- 6. Improvement 3: Brand Autopilot
- 7. Round 2 loose ends
- 8. Hardening and testing
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
