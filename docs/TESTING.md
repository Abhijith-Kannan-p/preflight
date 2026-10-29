# Testing

What was tested, how, and what came out, including what failed. Dates are 2026-10-29 unless
stated. "Local" is a Windows laptop (backend in Python 3.13, Postgres in Docker); "Render
simulation" is the production image in a container with Render's free-plan limits (512 MB,
no swap, 0.1 CPU; `deploy/render-sim.sh`); "production" is the live Vercel and Render site.

## Summary

| Area | How | Result |
|---|---|---|
| Unit and integration | pytest, 210 tests, real Postgres with a rollback per test | 210 passed |
| Main journeys J1 to J6 | Playwright, one spec per journey, local and production | 17/17 locally; 14/14 journey and page tests on production |
| Accessibility | axe (WCAG 2.0/2.1/2.2 A and AA) on 12 pages at 375, 768 and 1440 px | 0 violations of any impact in 36 page checks |
| Lighthouse accessibility | 9 pages, Lighthouse 12.2.1 mobile defaults | 100 on every page (target ≥ 95) |
| Layout | horizontal overflow on the same 12 pages × 3 widths | none |
| Concurrency | five visitors (five sandboxes) start reviews together | all five complete: 7–18 s locally, 34–114 s on production (one worker) |
| Manual checklist | scripted browser pass with a screenshot per step, production, 375 and 1440 px | 36/36 checks |
| Memory | Render simulation, every stage | see "Memory" |
| Evaluations | claims, held-out claims, full drafts, visual, compiler | see "Evaluations" |

## Unit and integration tests (pytest)

`cd backend && pytest` runs against a dedicated test database seeded once; each test runs in
a transaction that is rolled back. Models are replaced by deterministic fakes where a test is
not about them. 210 tests:

| File | Tests | Covers |
|---|---|---|
| test_visual.py | 26 | OCR mapping to text regions, palette, contrast, logo distortion and clear space, alt text, HTML emails |
| test_claims.py | 21 | Claim Ledger verdicts, numeric comparison, quotes, outdated and superseded facts |
| test_checkers.py | 18 | terminology, disclaimers, channels, readability, punctuation, tone |
| test_colour.py | 15 | CIEDE2000 against Sharma, Wu and Dalal's published pairs; WCAG contrast |
| test_bad_input.py | 14 | empty, whitespace, 20k+ characters, emoji and Hindi, renamed binary, password PDF, corrupt DOCX, 0-byte file, oversized image, unsupported type |
| test_ai.py | 12 | gateway retries, timeouts, circuit breaker, masking round trip, schema validation |
| test_normalise.py | 11 | PDF, DOCX, HTML and text intake |
| test_engine_core.py | 11 | pipeline, merging and ranking (a "needs a human look" finding never hides a confident one), Brand Score |
| test_workflow.py | 10 | state machine, permissions, approval gate, overrides with a reason |
| test_management.py | 9 | API keys, rate limit, webhook signatures, demo history, reset |
| test_sandbox.py | 8 | sandbox isolation, cloning, reset, expiry |
| test_compiler.py | 7 | brand-book extraction, schema, merge, accept/edit/reject, permissions |
| test_idempotency.py | 6 | repeated requests apply once, only successes are stored |
| test_seed.py | 5 | seed data integrity |
| test_governance.py | 5 | Radar dependency index, Guideline Health rates per version, reason grouping, Coach |
| test_webhooks.py | 4 | backoff (2 s, 4 s), final 4xx, three attempts, resend, events reach subscribers only |
| test_rulebook_api.py | 4 | rule and fact versioning |
| test_ml_runtime.py | 4 | ONNX runtime settings, lazy loading |
| test_config.py | 4 | settings parsing |
| test_voice.py | 3 | lexical features, fingerprint, adoption creates a version, tone uses it |
| test_health.py | 3 | /health states |
| test_eval.py | 3 | evaluation metrics |
| test_claim_scope.py | 3 | scope groups, hedged wording, "we" read as PayWise |
| test_review_queue.py | 2 | worker pool, queue positions |
| test_notifications.py | 2 | notifications pushed on commit, not on rollback; stream auth |

CI (`.github/workflows/ci.yml`) runs ruff, mypy, pytest, eslint, tsc and a production build on
every push.

## End to end (Playwright)

`cd e2e && npx playwright test`. `E2E_BASE_URL` and `E2E_API_URL` point the same specs at
production. Each journey from section 6 of the spec is its own spec:

| Spec | Journey | Checks |
|---|---|---|
| j1-core-review | J1 core review | landing → LinkedIn sample → margin notes → accept every suggestion → re-check → Brand Score rises (asserted below 50 before, 90 or more after) → submit → abhi4 approves → stamp → certificate with "Audit chain verified"; no browser console errors |
| j2-visual | J2 visual | festive banner → VIS-01, ACC-01 and CLM-04 on the image, overlay boxes → corrected design as revision 2 clears them → submit → approve → stamp |
| j3-governance | J3 governance | flagged rule → LLM rewording → published as the next version (checked through the API) → simulate F-087 → Radar lists items → Re-check now opens a review with CLM-03 → Coach tab → Coach panel on New review as abhi1 |
| j4-autopilot | J4 autopilot | compile the sample brand book → accept "revolutionary" → it appears in Terminology → adopt the Voice Fingerprint → the next review's tone targets equal the learned values (checked through the API) → compiler evaluation tab |
| j5-integrations | J5 integrations | create an API key → the curl example's request returns findings with CLM-04 and `blocking: true` → webhook to a 405 endpoint fails at once (1/3) → Resend → webhook to a refused port retries and ends failed at 3/3 |
| j6-robustness | J6 robustness | two browsers get private sandboxes and a reset touches only its owner; refresh straight after Run reattaches to the job; a double-click starts one review; 0-byte PDF, renamed binary and broken DOCX get specific messages and never a stack trace; a creator sees read-only screens and the API refuses an approval with a plain 403; a fresh sandbox shows empty states with a next action; five visitors' reviews all complete |
| a11y | accessibility and layout | axe and horizontal overflow on 12 pages at 375, 768 and 1440 px |
| pages, landing | other pages | settings, rulebook read-only for other roles, insights, evaluation tabs, landing |

**Local** (production build of the frontend, local backend): 17/17 passed.

**Production** (`E2E_BASE_URL=https://preflight-eight-smoky.vercel.app
E2E_API_URL=https://preflight-api-nauz.onrender.com`, one worker): the first run had 10 passed
and 4 failed. None of the four was a product defect, but each needed a fix:

| Failure | Cause | Fix |
|---|---|---|
| J1: Brand Score 24, expected ≥ 90 | Accepting every suggestion enables Submit on revision 1, and "revision 2" also appears in a tooltip, so on the slower host the test read revision 1's score | Wait until the dial itself shows revision 2's score |
| J3: no Radar entries after 30 s | Simulating the fact change took 19 s on production (see Performance: the database was in another region) | Database moved next to the server; the step allows 120 s |
| J5: `ECONNRESET` on the public API call | The host's proxy reset a reused keep-alive connection; the same call by hand returned 200 in 9.6 s | Retry once on a network error, as a client should |
| J6: 409 where 403 was expected | The test sent "approve" to a review that was not awaiting approval, so the state check answered first | Use a review that is in review |

Re-run of the four: 4/4 passed (J1 2.4 min, J3 2.9 min, J5 1.1 min, J6 50 s). Every journey
and page test has now passed on production.

## Accessibility

axe-core 4.10 through `@axe-core/playwright`, tags wcag2a, wcag2aa, wcag21a, wcag21aa and
wcag22aa, after the page's fade-in has finished. Pages: landing, dashboard, new review, a
review, queue, rulebook, governance, insights, evaluation, settings, a receipt and the 404 page,
as a Brand Manager (settings as the Admin).

First run: 33 serious findings, all fixed:

| Finding | Fix |
|---|---|
| White on brand teal #0F8B7E is 4.19:1 (buttons) | Button fill is the deep teal #0B6B61 (6.38:1); the brand teal stays for marks and accents |
| Stamp lines in cleared green at 90% opacity, 10 px | Deep cleared green #166842, full opacity (6.68:1) |
| White numbers on mid-teal confusion-matrix cells (2.5–3.0:1) | Ink numbers on every cell; the darkest fill is lighter |
| Scrollable confusion matrix and curl example not reachable by keyboard | Focusable (`tabIndex=0`), the curl block labelled |
| Receipt at 768 px scrolled sideways by 11 px | Certificate and hash values wrap in the stub column |
| Colours measured mid-animation (blended greys and teals) | Not a defect: the check now waits for animations to finish |

Second run: 0 violations of any impact (not only serious) in 36 page checks, no horizontal
overflow.

Lighthouse 12.2.1 (`node e2e/scripts/lighthouse.mjs <url>`, mobile emulation, local
production build; the 404 page is excluded because Lighthouse does not audit a 404 response):

| Page | Accessibility | Best practices | Performance | LCP |
|---|---|---|---|---|
| `/` | 100 | 100 | 93 | 2.9 s |
| `/app` | 100 | 100 | 76 | 5.3 s |
| `/app/review/new` | 100 | 100 | 75 | 5.1 s |
| `/app/queue` | 100 | 100 | 83 | 4.6 s |
| `/app/rulebook` | 100 | 100 | 81 | 5.1 s |
| `/app/governance` | 100 | 100 | 78 | 5.1 s |
| `/app/insights` | 100 | 100 | 81 | 4.9 s |
| `/app/evaluation` | 100 | 100 | 81 | 5 s |
| `/app/settings` | 100 | 100 | 80 | 5.1 s |

Performance is Lighthouse's simulated slow 4G on a mid-range phone; app pages wait for the
API to create a private demo workspace before they draw.

A first local run scored 100 on accessibility too, but every app page was stuck on "Waking up
the engine": the API refused the port by CORS. The script now reports console errors per page
and those runs must show 0.

## Performance

**Production before and after moving the database.** Render runs in Singapore; the Neon
database was in another region, so every query crossed continents (about 0.4 s per round trip).
It was moved to Neon in Singapore on 2026-10-29:

| Request | Before | After |
|---|---|---|
| `/health` (one query) | 1.05 s | 0.24 s |
| `/api/auth/me` | 1.26 s | 0.18 s |
| Simulate fact update (75 queries) | 18.8 s | 0.53 s |
| Five concurrent reviews (completion times) | 36–137 s | 34–114 s |

**Single reviews on production, warm, Gemini on** (`node e2e/scripts/visual-timing.mjs <API>`):

| Sample | Total | OCR |
|---|---|---|
| LinkedIn post (off-brand) | 28.1 s | — |
| Festive banner (image) | 42.6 s | 6.2 s |
| Scanned flyer (PDF) | 43.5 s | 9.4 s |
| Stretched logo (image) | 25.7 s | 8.4 s |
| Clean visual | 22.1 s | 6.0 s |
| HTML email | 6.3 s | — |
| Clean text post | 11.0 s | — |

The spec's target of a full review in 20 s or less on Render is met for clean and short drafts
and missed for the off-brand LinkedIn post (28 s) and the visual samples: on 0.1 CPU the NLI
model and OCR are the slow parts, and the LLM calls add a few seconds. Deterministic findings
stream to the page first, while the Claim Ledger is still running.

**Render simulation** (512 MB, 0.1 CPU, LLM off): cold start to a healthy server 53 s; demo
history ready 83 s after start; first text review 26 s (models load), warm text review 11 s,
visual review 31 s, brand book compiled 3 s, five concurrent reviews all done within 65 s.

**Local** (laptop): five concurrent reviews completed after 7, 8, 12, 14 and 18 s. The first
attempt reported 1–2 s because all five drafts were identical and came from the review cache;
each visitor's text is now unique.

## Memory

`bash deploy/render-sim.sh` builds the production image and runs it with 512 MB, no swap and
0.1 CPU and the settings from `render.yaml` (LLM off), then reads three figures after each
stage: the server process's peak resident memory (VmHWM), the cgroup's anonymous memory (what
cannot be given back), and the cgroup's peak (what the 512 MB limit counts):

| Stage | Time | Process peak | Anonymous | cgroup peak |
|---|---|---|---|---|
| Server up (cold start, migrations, seed) | 52.7 s | 240 MiB | 184 MiB | 195 MiB |
| Demo history generated (36 reviews, deterministic) | 82.6 s after start | 252 MiB | 188 MiB | 198 MiB |
| First text review (models load) | 25.8 s | 445 MiB | 290 MiB | 385 MiB |
| Text review, warm | 10.9 s | 445 MiB | 290 MiB | 385 MiB |
| Visual review (festive banner, OCR) | 30.8 s | 445 MiB | 295 MiB | 385 MiB |
| Brand book compiled (structured only) | 3.0 s | 445 MiB | 319 MiB | 385 MiB |
| Voice fingerprint | 0.3 s | 445 MiB | 319 MiB | 385 MiB |
| Five visitors at once (five sandboxes, five reviews) | 65.3 s for all | 474 MiB | 327 MiB | 385 MiB |

No out-of-memory kill and no restart. About 96 MiB of the process figure is file-backed pages
of shared libraries (ONNX Runtime, numpy, OpenCV), which the container is not charged for; by
the measure the 512 MB limit enforces the peak is 385 MiB, under the 450 MiB budget. By the
process's own high-water mark it is 445 MiB for any single review and 474 MiB with five
visitors arriving together, above the budget. On a cold page cache (first run on a fresh
machine) the cgroup peak reached the 512 MiB limit once, because model files read from disk
are cached; the kernel reclaims that cache, and anonymous memory stayed at 290–330 MiB.
Sandbox clones are now serialised (each holds the template's audit chain in memory): 479 → 474
MiB process peak with five visitors.

## Evaluations

Every evaluation has a script, a labelled set in `data/eval/`, and its result on the
Evaluation page.

| Evaluation | Script | Set | Result |
|---|---|---|---|
| Claim Ledger | `python -m app.eval.run` | 150 labelled claims | accuracy 0.96, macro recall 0.96, problem-claim recall 1.00, `unsupported` precision 0.94 (target 0.90) |
| Claim Ledger, held out | `python -m app.eval.run --dataset claims_holdout.jsonl` | 27 claims written after the Round 3 rules were tuned | accuracy 0.78, problem-claim recall 0.86, `unsupported` precision 0.67 |
| Full drafts | `python -m app.eval.drafts` | 20 drafts, 27 labelled issues, 7 clean | precision 0.92, recall 0.89, 15/20 exactly right, 7/7 clean drafts pass |
| Visual review | `python -m app.eval.visual` | 100 labelled assets | precision 1.00, recall 0.99, OCR words read 98.3% |
| Rulebook Compiler | `python -m app.eval.compiler` | 51 hand-labelled rules in the sample brand book | with Gemini (mean of 3 runs): recall 94%, precision 100%, acceptable without edits 100%, right page 100%; structured only: 82% / 100% / 98% |

The 150-claim set was used to tune the Round 3 claim rules, so its numbers flatter them; the
held-out set is the honest generalisation figure. The visual set is synthetic.

## Manual exploratory checklist (production)

`node e2e/scripts/exploratory.mjs <frontend> <API> <screenshot dir> <width>` walks the list
below in a real browser on production and saves a full-page screenshot after every step; the
screenshots were then looked through by eye. Run at 375 px (phone) and 1440 px (desktop):
36/36 passed.

| Check | 375 px | 1440 px |
|---|---|---|
| Landing loads, no sideways scroll | pass | pass |
| "Open the demo desk" gives a private session | pass | pass |
| Whitespace-only text: Run stays disabled | pass | pass |
| Over 20,000 characters: the editor stops at 20,000 | pass | pass |
| Emoji and Hindi text is reviewed (score 100, nothing flagged) | pass | pass |
| Back and forward between New review and a review | pass | pass |
| Review page has no sideways scroll | pass | pass |
| `?` opens the help sheet, J moves between findings | pass | pass |
| Refresh straight after Run reattaches to the review | pass | pass (after fixing a script race, below) |
| 6 MB image refused before upload ("5 MB or smaller") | pass | pass |
| Unsupported file type gets a message | pass | pass |
| A creator's approve call: "Your role cannot approve content." | pass | pass |
| Unknown address shows the styled 404 | pass | pass |
| Dashboard, rulebook, governance, evaluation, settings: load, no sideways scroll | pass | pass |

Observations from the screenshots:
- At 375 px the main navigation is a sideways-scrolling strip and the last items were simply
  cut off ("Evalua…") with nothing to say there was more. The strip now fades at the right
  edge, ends with a little space and marks the current page.
- The first 1440 px run read the draft before the sample text had loaded, so it reviewed only
  the reference number; fixed in the script, then passed twice.
- A draft that is only a reference number ("Ref 1793271317383") gets a "Factual claims need an
  approved fact" finding: harmless, but not a claim.
- During the heavy test runs Gemini's free tier rate-limited the app; the page showed "AI
  checks temporarily limited" and the offline fallbacks took over, as designed.

## Bugs found by testing and fixed

Found by the tests, evaluations or checks above and fixed (Round 3):

| Found by | Bug | Fix |
|---|---|---|
| Full-draft evaluation | A low-confidence tone finding on a sentence hid a confident punctuation finding on the same sentence (merge ranked by severity × confidence) | Confident findings always rank first when duplicates merge; unit test added |
| Full-draft evaluation | Claims written as "we" ("We settle payments in 3 seconds") were not compared with facts about PayWise | "We/our" at the start of a claim is read as PayWise |
| Claim evaluation | Local template facts had no embeddings after a reseed without the model, silently disabling dense retrieval | Missing fact embeddings are filled in at boot, in every workspace |
| Claim evaluation | Production would keep showing the old evaluation run | Runs record `LEDGER_VERSION`; an older latest run is replaced at boot |
| Workflow test | A scope rule hid a real contradiction (Business merchant, Card fee) | Products removed from the scope groups |
| axe | Contrast and keyboard issues listed under Accessibility | Fixed as listed |
| Layout check | Receipt scrolled sideways at 768 px | Values wrap |
| e2e (J4) | The compile progress stream reopened on every render, so the page never updated | Callback held in a ref |
| Compiler evaluation | A wrapped table cell kept its line break; one malformed LLM item failed the whole answer | Cells normalised; items validated one by one |
| e2e (J5) | Patching the thread class in a test replaced it for the review runner too | Webhooks start work through their own helper |
| Lighthouse | First run audited a loading screen (CORS) and still scored 100 | Script reports console errors; runs must show 0 |
| Concurrency test | Five identical drafts came from the review cache in 1–2 s | Each visitor's text is unique |
| Production timings | Every database round trip cost about 0.4 s (server in Singapore, database in another region) | Database moved to Neon in Singapore: 19 s → 0.5 s for the fact-update simulation |
| Exploratory screenshots | Mobile navigation cut off with no sign of more items | Right-edge fade, end spacing, current page marked |
| Earlier phases | Offline tone heuristic flagged two-thirds of on-brand drafts; a role switch during the first session load was dropped; OCR beside NLI peaked at 504 MiB in 512 MB | Heuristic tone findings wait for a person; queued session switches; NLI released during OCR |

## Known remaining issues

- Claim Ledger on held-out claims: `unsupported` precision 0.67; hedged wording outside the word list is still called unsupported, two vague claims are not detected, and "PayWise Pay Later has no late fees" was judged supported.
- Full drafts: a year inside a compound sentence ("Founded in 2017 in Bengaluru, we…") is not compared with the founding-year fact.
- Memory: the server process's own peak reaches 474 MiB with five visitors arriving together (385 MiB by the container's accounting).
- Speed on Render's 0.1 CPU: the off-brand LinkedIn post takes 28 s and visual reviews 22–44 s on production, above the 20 s target; five reviews at once finish one after another (one worker), the last after about two minutes.
- Gemini's free tier rate-limits under heavy use; the offline fallbacks then score tone and word suggestions.
- A line that is only a number is treated as a factual claim.
- Webhooks can target any URL, including private addresses; a production service would block those (SSRF).
- Lighthouse performance on app pages is 75–83 under mobile throttling: each first visit creates a private demo workspace before drawing.
