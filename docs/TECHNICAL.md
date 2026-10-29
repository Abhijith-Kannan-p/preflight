# Technical details

## Architecture

```
frontend/   Next.js 15 (App Router), React 19, TypeScript, Tailwind ("Proof Desk" tokens), SWR,
            framer-motion, Recharts
backend/    Python 3.11, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic
  app/engine/        normaliser, checkers, Claim Ledger (detect, retrieve, scope, quantities,
                     quote), merger, drift, Brand Score, validator
  app/visual/        intake (images, scans, HTML), OCR, palette, contrast, logo, alt text
  app/governance/    Guideline Health, rewording, Stale-Content Radar, Creator Coach, Voice Fingerprint
  app/compiler/      brand-book reader, structured and LLM extraction, typed schema, matcher, apply
  app/ai/            masking, provider gateway (Gemini / Groq / none), tone, claim extraction, suggestions
  app/ml/            ONNX embedder and NLI, lazy loading, memory trimming
  app/api/           REST endpoints (reviews, rulebook, governance, compiler, receipts, insights,
                     evaluation, settings, sandbox, public v1)
  app/services/      review job queue and runner, SSE event bus, sandboxes, webhooks, notifications,
                     rate limiter, demo history, receipt PDF
  app/eval/          claims, full drafts, visual and compiler evaluations
data/seed/     fictional PayWise brand: rules, facts, terms, channels, confidential terms,
               samples, six-week review history
data/samples/  the fictional 20-page PayWise Brand Book (PDF)
data/eval/     150 + 27 held-out claims, 20 full drafts, 100 visual assets, brand-book labels,
               and the precomputed runs
e2e/           Playwright: J1-J6 journeys, accessibility and layout; scripts for Lighthouse,
               load, timing and the exploratory checklist
deploy/        Render simulation (render-sim.sh), Hugging Face Space package
```

Hosting: frontend on **Vercel**; backend on **Render's free plan** (512 MB RAM, 0.1 CPU,
Singapore) from `render.yaml`; Postgres with pgvector on **Neon** in the same region (an
earlier database in another region cost about 0.4 s per query round trip). `deploy/hf-space/` holds an equivalent Hugging
Face Docker Space package.

## Data flow for one review

```mermaid
sequenceDiagram
  participant U as Browser
  participant A as FastAPI
  participant R as Runner thread
  participant E as Engine
  participant G as AI gateway
  participant D as Postgres
  U->>A: POST /api/reviews (text, DOCX or PDF)
  A->>A: normalise into blocks with offsets
  A->>D: Submission + Revision 1, audit "created"
  A->>R: start review
  A-->>U: 201 {id}
  U->>A: GET /api/reviews/{id}/events (SSE)
  R->>D: load rulebook + facts snapshot (cache by content hash + versions)
  par checkers run concurrently
    R->>E: terminology, disclaimers, channel, readability, style
    E-->>U: checker_done (deterministic, under 2 s)
  and
    R->>E: tone
    E->>G: mask → Gemini (8 s timeout, 1 retry) → validate → unmask
  and
    R->>E: Claim Ledger
    E->>G: LLM claim proposals (masked)
    E->>E: BM25 + bge-small dense + RRF, NLI, numbers, quote check
  end
  R->>E: merge, rank, suggestions (rule wording first, LLM for the rest), drift, Brand Score
  R->>D: findings, ledger, AI call log, report; audit "review_completed"
  R-->>U: review_complete
  U->>A: decisions, re-check, submit, approve (gate) → receipt + webhook
```

## Findings

Every checker returns the typed `Finding` contract (`app/engine/schema.py`): type, span
(block, start, end), text, rule (ID and source page), evidence (fact ID, verbatim quote, NLI
label, score), severity, confidence, explanation, suggestion (text, drift), detector, status.
`app/engine/validate.py` **rejects** any finding that cites an unknown rule or fact ID or
whose span text does not match the document, whatever produced it.

The merger keeps findings separate unless they cite the same rule on overlapping text or
cover nearly the same span (IoU ≥ 0.8) with the same type; duplicates are attached as
`related`. Findings with confidence < 0.6 go to "Needs a human look" and cost no points.

**Brand Score** = max(0, 100 − 25 × critical − 10 × major − 3 × minor) over open findings.

**Drift** = 1 − cosine(embed(original sentence), embed(sentence with the suggestion applied)),
labelled low (< 0.15), medium (< 0.35) or high; a word-overlap distance is used if the
embedding model is unavailable.

## Claim Ledger

1. **Detect.** Pattern rules (numbers, durations, percentages, superlatives, absolutes,
   guarantees, "free"), compound-sentence and relative-clause splitting ("PayWise, which is
   regulated…, serves…" becomes two claims), plus LLM proposals that must be verbatim
   substrings of the draft. Unioned and de-duplicated by span.
2. **Retrieve.** Over current facts and, separately, superseded facts: BM25 (rank-bm25) and
   dense cosine over bge-small embeddings stored in a pgvector column, fused with reciprocal
   rank fusion (k = 60), top 5 current and top 3 superseded.
3. **Verify.** A local cross-encoder (`cross-encoder/nli-deberta-v3-xsmall` as its official
   int8 ONNX export, premise = fact, hypothesis = claim) gives entailment, contradiction and neutral probabilities. **Exact
   numeric comparison** extracts quantities with families (time in seconds, counts with the
   counted noun, fees, ratings, currency); a mismatch on the same topic is a contradiction
   regardless of NLI. Rule phrases such as "100% secure" are masked out first so they are not
   compared as percentages.
4. **Quote check.** A `supported` verdict must cite a run of at least three words found
   verbatim in the fact; otherwise it is downgraded to `needs_review`.
5. **Scope.** Before any fact may judge a claim, facts about a different payment method
   (UPI, card, net banking, wallet) or app store (Google Play, Apple) than the claim names are
   set aside: "10% cashback on UPI" is not contradicted by the card's 1% cashback. Products are
   not a scope group, because they overlap (a Business merchant pays Card fees). Claims
   written as "we" or "our" are read as PayWise for retrieval and NLI.
6. **Decide.** Entailment ≥ 0.7 with a current fact and a valid quote → supported. Matches a
   superseded fact whose successor differs → outdated (with the current fact). Contradiction
   ≥ 0.6 with a clearly on-topic current fact (similarity ≥ 0.74 for numbers, ≥ 0.75 for NLI
   alone) → contradicted. Ambiguous 0.4–0.6 → needs_review. Hedged wording with no number to check
   ("trusted by millions", "cheaper than most") → needs_review. Otherwise unsupported.
   Because the small NLI model rejects true paraphrases that add harmless detail, a
   deterministic support path also accepts a claim when the numbers match exactly (or a
   verbatim quote covers most of it) on an on-topic fact with no contradiction, at
   confidence 0.75.

Every step is recorded and shown under "How this verdict was reached". **The LLM never
decides truth**: it can only propose claims and wording.

## AI gateway

`app/ai/gateway.py`: `mask → provider → JSON parse → Pydantic validation → unmask`, with an
8 s timeout, one retry, then `None` so callers fall back. Three consecutive failures open a
circuit breaker that forces deterministic mode for 60 s. Providers: Gemini
(`gemini-3.5-flash-lite`, JSON response mode), Groq (OpenAI-compatible JSON mode), or none.
Every call is logged (purpose, provider, model, latency, tokens, values masked) and
summarised in the "AI used in this review" panel and on the receipt.

`app/ai/masking.py` replaces confidential terms from the Brand Knowledge Base, emails, Indian
phone numbers and ₹ amounts with stable tokens (`[CONFIDENTIAL_1]`, `[PRICE_1]`) and restores
them in the response; the round trip is unit-tested.

Suggestions use the rule's brand-approved fallback wording first; the LLM rewrites only the
flagged phrase for the rest, limited to approved facts. Rewrites that are much longer than the
phrase or introduce a number not present in the sentence or an allowed fact are rejected.

## Data model

`Workspace`, `User`, `Rule` (code + version; edits retire the old version), `Fact` (validity
dates, `superseded_by`, `embedding vector(384)`), `Term`, `ChannelProfile`,
`ConfidentialTerm`, `SampleDraft`, `Submission` (state), `Revision` (normalised document,
content hash, report), `Finding`, `Claim` (ledger row with steps), `Decision`, `Comment`,
`Notification`, `AuditEvent`, `AiCall`, `ApiKey` (SHA-256 hash only), `Webhook`,
`WebhookDelivery` (status, attempts and every attempt, the payload for resending),
`EvalRun` (with the ledger version that produced it), `IdempotencyKey`, `RevisionAsset`
(images and page renders), `CompileJob` and `RuleCandidate` (the compiler's review queue).
Workspaces have a kind (`template` or `sandbox`), a voice profile with version history and
rulebook and factbook versions. Migrations: Alembic, run on every start.

**Audit log**: append-only `(id, entity, entity_id, action, actor_id, payload_json, ts,
prev_hash, hash)` with `hash = sha256(prev_hash + canonical_json(event))`. Appends take a
Postgres advisory lock so concurrent requests cannot fork the chain. `GET /api/audit/verify`
recomputes the chain and reports the first broken link; a test edits an event and checks
that verification fails.

## Workflow and permissions

Draft → In review → Changes requested → In review → Approved → Published; illegal transitions
return 409. Submitting requires no open critical findings (disputed ones may go to the
approver); approving requires every remaining critical to be overridden with a written
reason, which is highlighted on the receipt. Permissions follow the Round 1 table and are
enforced in the backend (`app/auth.py`); demo sign-in issues a signed JWT per seeded user.

## Per-visitor sandboxes

The seeded PayWise workspace is a **template**. The first request of a new browser (through
the frontend's `/api/sandbox/*` rewrite, so the httpOnly cookie is first-party) clones it in
the database: rules, facts with embeddings, terms, channels, palette, samples, the review
history with findings, claims and decisions, and the five personas with suffixed ids
(`usr_abhi1_3f2a…`). The audit chain is re-chained for the copy. Everything is scoped by
`user.workspace_id`, so a visitor never sees another's data; "Reset my demo workspace" clears
and re-clones only theirs (fresh persona ids, versions moved forward so no cached result is
reused). A sweeper deletes sandboxes idle for 24 hours. Clones run one at a time (each holds
the template's audit chain in memory). Cloning takes about 0.1 s locally. Reviews are cached by a context fingerprint (content, channel, rulebook and
factbook content), so identical sandboxes share results safely; a cached review is labelled.

## Visual review

Images (PNG, JPG, WebP up to 5 MB, 40 MP decompression guard), scanned PDFs (pages with
little text layer are rendered at 150 dpi, at most 5) and HTML emails go through
`app/visual/`:

1. **OCR**: RapidOCR (PP-OCRv4 detection and recognition on ONNX Runtime) on a copy reduced
   to 736 px (960 px for scans); lines grouped into paragraph blocks with a per-line layout,
   so every text finding is also drawn on the image. The logo's own letters are removed.
2. **Text checks**: the OCR text becomes the document and every text checker runs on it.
3. **VIS-01 palette**: k-means (k = 6) on a thumbnail; colours over 8% of the image more than
   ΔE00 10 (CIEDE2000, our numpy implementation tested against the published reference pairs)
   from every brand colour.
4. **ACC-01 contrast**: per OCR line, the WCAG 2.2 ratio of text pixels to the box's edge
   colour; 4.5:1, or 3:1 for large text.
5. **VIS-02 / VIS-03 logo**: OpenCV template matching confirmed by the brand teal; the tile's
   aspect ratio (over 5% off is distortion) and a clear-space ring of a quarter of the logo
   height.
6. **ACC-02 / ACC-03 alt text**: missing, empty, file-name or "image of…" alt text.

On a 512 MB host (`OCR_EXCLUSIVE=true`) the NLI model is released while an image is read, so
the two models never share memory.

## Governance intelligence

All three views are computed from data the workflow already records, nothing extra is
stored:
- **Guideline Health**: per rule and per rule version (by the time each version was active),
  findings raised once per review, dispute, override and acceptance rates,
  `ambiguity = 0.6 × dispute rate + 0.4 × override rate` (from 4 findings, flagged at 30%),
  dispute reasons grouped by word-stem overlap; the LLM rewording is published as a new rule
  version through the normal rulebook endpoint.
- **Stale-Content Radar**: an index from cleared items → cleared revision → claims → the
  facts their evidence cited, with the fact's wording at review time. Every fact update,
  supersession or retirement looks up the index in the same transaction and notifies the
  authors and brand managers; "Re-check now" opens the cleared text as a new review.
- **Creator Coach**: per author, first-draft findings in time order; a repeat mistake is a
  rule that already flagged one of their earlier first drafts. Tips come from the rule's
  guidance, its approved wording and the author's own last fix.

## Rulebook Compiler and Voice Fingerprint

The compiler (`app/compiler/`) runs as a background job with five stages streamed over SSE:
read the document with page numbers (PyMuPDF, tables with `find_tables`; DOCX by heading);
structured extraction (tables, word lists, colours, numeric limits, quoted phrases under claim
headings, "must include" disclaimers); one masked LLM call for prose rules; a typed schema
(term, word, pattern, disclaimer, colour, channel, threshold, voice, guidance), each item
validated on its own; and a comparison with the workspace's rulebook (same term, pattern or
limit; ΔE00 < 3 for colours; embedding similarity ≥ 0.82 for prose guidance). Candidates wait
in `rule_candidates`; accepting one writes a new rule version (or term, colour, channel limit,
voice profile) cited to the brand book and page, bumps the rulebook version and is
audit-logged. Without the LLM the structured stage still runs and the page says what is
missing.

The Voice Fingerprint (`app/governance/voice.py`) averages the tone scores stored with every
approved item's latest review and adds lexical habits per 100 words. Adopting it writes a new
voice-profile version (the old one kept, audit-logged); the tone checker reads the profile in
force when a review starts. Its effect is measured as the tone-dispute rate per profile
version, plus a replay of stored scores against the learned targets.

## Reliability

- Reviews are jobs on a small worker pool (`REVIEW_WORKERS`) with queue positions, a
  120 s budget and re-queueing after a restart, so a reloaded page reattaches. Progress
  streams over SSE with replay for late subscribers, reconnection with backoff, a stall state
  after 60 s and polling as a fallback. Every request gives up after 45 s with a message.
- Every write accepts an `Idempotency-Key`; repeated decisions on a finding are no-ops, so
  double clicks never duplicate anything.
- Models load once in a background thread at boot; `/health` reports `models_ready` and the
  frontend shows "Waking up the engine…" until then. The Docker image bakes both models in
  and runs with `HF_HUB_OFFLINE=1`, so start-up never depends on huggingface.co.
- Results are cached by (content hash, channel, rulebook version, factbook version); any
  rule or fact edit bumps a version.
- Input limits: 5 MB files, 20,000 characters, 1 MB CSV imports; friendly errors for
  password-protected, scanned or corrupt files.
- Public API rate limit: 30 requests per minute per key (HTTP 429 with Retry-After).
- Webhooks (`submission.approved`, `review.published`, `finding.critical`, chosen per
  webhook) are signed with HMAC-SHA256 (`X-Preflight-Signature: sha256=…`). Each delivery
  gets up to 3 attempts (waits of 2 s and 4 s; network errors, 5xx, 408 and 429 are retried),
  every attempt is logged, and any delivery can be resent.
- Notifications are pushed over SSE (`/api/notifications/stream`) when the transaction that
  created them commits; the header polls every 15 s only while the stream is down.

## Evaluation

`data/eval/claims.jsonl` holds 150 hand-written PayWise claims: 45 supported, 20 outdated,
35 contradicted, 35 unsupported, 15 needs_review, each tied to the fact that decides it.
`python -m app.eval.run` runs the real ledger on each and stores an `EvalRun`; the app
precomputes one at boot and shows it on the Evaluation page.

| Verdict | Precision | Recall | F1 | n |
|---|---|---|---|---|
| supported | 1.00 | 0.93 | 0.97 | 45 |
| outdated | 1.00 | 1.00 | 1.00 | 20 |
| contradicted | 0.97 | 0.97 | 0.97 | 35 |
| unsupported | 0.94 | 0.97 | 0.96 | 35 |
| needs_review | 0.82 | 0.93 | 0.88 | 15 |

Accuracy 0.96, macro recall 0.96 (plan target ≥ 0.85, met), problem-claim recall 1.00,
`unsupported` precision 0.94 (plan target 0.90, met on this set). Round 3 added two rules:
hedged wording with no number ("trusted by millions", "cheaper than most") goes to a person,
and facts about a different payment method or app store are set aside before they can
support or contradict a claim. Claims written as "we" are read as PayWise.

These rules and the similarity thresholds were tuned on this set, so it flatters them.
`data/eval/claims_holdout.jsonl` holds 27 claims written afterwards: accuracy 0.78,
`unsupported` precision 0.67, problem-claim recall 0.86. Misses there: hedged wording outside
the word list, two vague claims not detected as claims, and "PayWise Pay Later has no late
fees" judged supported.

`data/eval/full_drafts.json` holds 20 complete drafts labelled with the rules a reviewer
would raise (7 clean). `python -m app.eval.drafts` reviews each with every checker: precision
0.92, recall 0.89 over (draft, rule) pairs, 15 of 20 drafts exactly right, all 7 clean drafts
pass.

## Running in 512 MB

Both text models are int8 ONNX files run by ONNX Runtime (no PyTorch); OCR uses ONNX models
too. What makes it fit (`app/ml/`): graph optimisation off (it expanded the int8 weights to
408 MiB at load), no memory arena, one thread; SentencePiece instead of `tokenizers` for the
128k DeBERTa vocabulary (56 vs 106 MiB); `NLI_BATCH_SIZE=2`; `MODEL_LOADING=lazy`; the NLI
model released while OCR runs (`OCR_EXCLUSIVE`); `malloc_trim` after each review and
`MALLOC_ARENA_MAX=2`; sandbox clones one at a time; and the evaluation loaded from
`data/eval/precomputed_run.json`. Models are downloaded during the build and used with
`HF_HUB_OFFLINE=1`. If a model fails to load, the Claim Ledger falls back to numeric and
lexical checks and every deterministic checker still runs.

`bash deploy/render-sim.sh` runs the production image with 512 MB, no swap and 0.1 CPU:

| Stage | Server process peak | Container (cgroup) peak |
|---|---|---|
| Server up, demo history generated | 252 MiB | 198 MiB |
| First text review (models load) | 445 MiB | 385 MiB |
| Visual review, compiler, fingerprint | 445 MiB | 385 MiB |
| Five visitors at once | 474 MiB | 385 MiB |

No out-of-memory kill or restart. The container figure is what the 512 MB limit counts; the
process figure also includes about 96 MiB of shared-library pages the container is not charged
for. Details: [TESTING.md](TESTING.md#memory).

## Testing

210 backend tests (pytest, a real Postgres with a rollback per test), Playwright specs for the
six main journeys plus accessibility and layout at three widths, run locally and against
production, and CI (ruff, mypy, pytest, eslint, tsc, production build) on every push. Every
result is in [TESTING.md](TESTING.md).
