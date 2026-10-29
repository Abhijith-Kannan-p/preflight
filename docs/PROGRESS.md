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

- 8. Hardening and testing (2026-10-29): J1–J6 as separate Playwright specs (local 17/17;
  production 14/14 after fixing four test issues); axe on 12 pages × 3 widths (33 serious
  findings fixed, now 0 of any impact); Lighthouse accessibility 100 and best practices 100 on
  9 pages; exploratory checklist on production 36/36 with screenshots; Render simulation script
  with memory per stage; production found to cross continents for every query (0.4 s round
  trips): database moved to Singapore, fact-update simulation 19 s → 0.5 s. Results in
  `docs/TESTING.md`. Tests: backend 210, e2e 17.

- 9. Documentation and handover (2026-10-29): README rewritten for Round 3 (live link and
  demo at the top, screenshots, features, architecture, environment variables, clone and run,
  results, deployment, limitations); TECHNICAL, FEATURES, ROUND3_IMPROVEMENTS (results table and
  other improvements), TESTING, new ROADMAP, demo script. README instructions followed from a
  fresh clone: the Docker path needed two fixes (no stylesheet when built in `/app`; sandbox
  proxy pointed at the container itself), after which 10/10 tests passed against it; the
  no-Docker path passed as written. Production: axe clean at three widths, Lighthouse
  accessibility 100 on every page.

## In progress
- None. All nine build steps are complete.

## Next
- After the competition: see ROADMAP.md.

## UI refresh (final round)

Visual and interaction design only; all functionality unchanged.

- U1. Theme and navigation (2026-10-29): Night Desk (dark) and Paper Desk (light) tokens,
  following the system until the visitor picks one in the header (stored in localStorage);
  the proof sheet, certificate, stamp, error sheet and splash stay a lit paper sheet in both
  themes (`.proof-paper`); primary actions are ivory on the night desk; radius scale
  0 / 6 / 10 / 999. Header: six sections (Review, Queue, Rulebook, Governance, Evaluation,
  Settings) with a section accent line, a sub-nav row for Review and Governance (Governance's
  tabs and Insights), one "Demo · AI on" status pill, a theme toggle, and below 1024 px a menu
  drawer. axe in both themes at 375 / 768 / 1440 px: 0 violations after fixing the input fill
  and the confusion-matrix contrast in Night Desk. e2e 21/21.
- U2. Proof sheet and margin notes (2026-10-29): every marked span carries a numbered marker
  in its severity colour (reading order), matching its note; notes sit level with the line of
  their mark and stack below each other on a shared line; the sheet grows to the notes' height
  and its text stays in view beside them; one connector, only for the note being pointed at or
  opened; compact notes (number, severity, one-line reason, the fix, Accept) expand on click or
  Enter (rule, confidence, evidence, Edit / Dispute / Escalate); a summary bar ("Not ready to
  publish", severity filter chips, "Accept all suggested fixes" with an idempotency key per
  note); the legend in a "?" popover. Same on the visual desk (numbered boxes on the image) and
  the landing specimen; inline numbered notes below 1024 px. e2e 22/22 (new: accept all,
  filters, double click), axe clean in both themes.
- U3. Intro before the landing page (2026-10-29): a perspective tunnel of ten review pieces
  (the LinkedIn draft, a CLM-04 note, fact F-087, the festive banner with its VIS-01 box, Brand
  Score 24 and 97, the stamp, a certificate stub with QR, an OUTDATED ledger row, the palette)
  flying from z −1700 to +500 px on staggered windows, golden-angle spread, spring-smoothed
  pointer parallax, a dot grid and ring guides, "Every claim, cleared." scaling up. Driven by
  the page's own scroll through a sticky stage (1.75 viewports of travel), so wheel, trackpad,
  touch and keys all work and nothing is intercepted; stopping in the last stretch glides on to
  the landing page, scrolling up replays it, "Skip intro" (top right and bottom) jumps there;
  reduced motion gets a still composition with Continue; the session remembers it (pre-paint,
  so no flash) with "Replay intro". Six cards on phones. Replaces the 2-second splash. The
  landing page itself is unchanged. Fixed on the way: the landing specimen scrolled its open
  note into view on arrival; card positions differed between server and browser rendering.
  e2e 26/26 (new intro spec: wheel, keys, skip, reverse, session memory, reduced motion,
  phone). Touch on a real phone is a manual check: headless Chrome's synthetic touch gestures
  do not scroll any page.
- U4. Depth and variety (2026-10-29): a section icon chip tinted with the section's accent in
  every page header; page intros cut to one sentence with "How this works" for the rest; plain
  sans labels (mono capitals kept for kickers and table headers); body text 15 px; metrics and
  the Brand Score in serif display numbers; checklist states as coloured icon chips with ticks
  that pop in; empty states with our own line drawing; the certificate keeps its print labels
  and its punched holes show the dark desk. Sub-navigation rendered on the server so app pages
  do not shift (Lighthouse back to 71–84 from about 60).
- U5. Tests, screenshots, docs (2026-10-29): e2e 26/26 on a production build, axe clean on 72
  page checks (12 pages × 3 widths × 2 themes), Lighthouse accessibility 100 on 9 pages,
  exploratory checklist 54/54 at 375 / 768 / 1440 px. Eighteen screenshots (nine scenes, both
  themes) in `docs/images/` from `e2e/scripts/readme-shots.mjs`; README, TESTING ("UI
  refresh"), FEATURES, CHANGES_FROM_PLAN, DEMO_SCRIPT updated.

### UI refresh 2 (murmuration hero, connected notes, Warm Night Desk)

- W1. Warm Night Desk (2026-10-30): the dark theme moves to warm near-black (#1C1816 desk,
  #241F1C cards, #2B2522 raised, #3A332E hairlines, ivory #EDE6DC text). Teal #2BA89A is the one
  accent: primary actions (dark text #10201E), links, focus rings, active tabs and the section
  line; per-section colours are gone. Red, amber and blue now appear only for severities (plus
  red for Delete, blocked and failed states): read-only notices, the AI-fallback chip, review
  states, the notification badge, diff deletions and evaluation tags became teal or neutral.
  Oxblood #9B1C1C logo mark and favicon. The proof sheet and certificate stay lit paper, with a
  faint warm desk-lamp glow and paper grain in the dark theme. axe clean in both themes at 375 /
  768 / 1440 px; J1–J6, pages and landing 15/15.
- W2. Murmuration hero (2026-10-30): the scroll tunnel intro, its session memory and "Replay
  intro" are gone. The landing page opens on a full-height sky where about 3,000 starlings (fewer
  on small screens, by area) fold, converge into PREFLIGHT, hold it and scatter; the pointer or a
  finger is a hawk they flee. Letters sampled from Newsreader at 800. Dusk preset (near-black
  birds and reeds against a warm horizon) on the Warm Night Desk, paper preset on Paper Desk,
  switching live with the theme. Kicker, "Every claim earns its place." and the two actions are
  server-rendered over a soft scrim; the canvas starts after hydration, pauses off-screen and in
  hidden tabs, and with reduced motion draws the formed word once. Landing Lighthouse 95
  (was 91), first-load JS 133 kB; full suite 25/25 with a new hero spec.
- W3. Connected margin notes (2026-10-30): every visible note is joined to its mark by an
  orthogonal elbow: down from the numbered marker into the line spacing, right to its own lane
  in a widened gutter, along the lane to the note's level, into the number badge. Lanes follow
  reading order so connectors never cross one another's verticals or pass over a note. Lines
  are 1 px at 35% in the severity colour (teal once settled); the active note's is 2 px at full
  strength. Redrawn on resize, font load, expand and collapse (following the notes' slide frame
  by frame), filtering, re-check and scroll (the text is sticky). Same on the landing specimen
  and visual reviews (from each box). Inline notes without lines below 1024 px.
- W4. Tests, screenshots, docs (2026-10-30): connectors spec plus checks in J1 and J2; full suite
  26/26, axe clean in both themes at three widths, Lighthouse accessibility 100 on 9 pages,
  exploratory 54/54. Primary buttons, the avatar and tooltips no longer ivory on the dark desk.
  Eighteen screenshots regenerated (hero replaces intro); README, TESTING ("UI refresh 2"),
  FEATURES, DEMO_SCRIPT, AI_AND_LIBRARIES, CHANGES_FROM_PLAN updated.

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
