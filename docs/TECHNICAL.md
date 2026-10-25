# Technical details

## Architecture

```
frontend/   Next.js 15 (App Router), React 19, TypeScript, Tailwind, SWR, framer-motion, Recharts
backend/    Python 3.11, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic
  app/engine/        normaliser, checkers, Claim Ledger, merger, drift, Brand Score, validator
  app/ai/            masking, provider gateway (Gemini / Groq / none), tone, claim extraction, suggestions
  app/api/           REST endpoints (reviews, rulebook, receipts, insights, evaluation, settings, public v1)
  app/services/      review runner, SSE event bus, webhooks, rate limiter, demo history, receipt PDF
  app/eval/          labelled-set runner and metrics
data/seed/  fictional PayWise brand: rules, facts, terms, channels, confidential terms, samples, history
data/eval/  150 labelled claims
e2e/        Playwright tests
```

Hosting: frontend on **Vercel**; backend on **Render's free plan** (512 MB RAM, 0.1 CPU) from
`render.yaml`; Postgres with pgvector on **Neon**. `deploy/hf-space/` holds an equivalent Hugging
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
5. **Decide.** Entailment ≥ 0.7 with a current fact and a valid quote → supported. Matches a
   superseded fact whose successor differs → outdated (with the current fact). Contradiction
   ≥ 0.6 with a clearly on-topic current fact (similarity ≥ 0.74 for numbers, ≥ 0.75 for NLI
   alone) → contradicted. Ambiguous 0.4–0.6 → needs_review. Otherwise unsupported.
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
`WebhookDelivery`, `EvalRun`. Migrations: Alembic.

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

## Reliability

- Reviews run in worker threads with their own event loop, so CPU-bound NLI never blocks
  the API. Progress streams over SSE with replay for late subscribers, plus polling as a
  fallback.
- Models load once in a background thread at boot; `/health` reports `models_ready` and the
  frontend shows "Waking up the engine…" until then. The Docker image bakes both models in
  and runs with `HF_HUB_OFFLINE=1`, so start-up never depends on huggingface.co.
- Results are cached by (content hash, channel, rulebook version, factbook version); any
  rule or fact edit bumps a version.
- Input limits: 5 MB files, 20,000 characters, 1 MB CSV imports; friendly errors for
  password-protected, scanned or corrupt files.
- Public API rate limit: 30 requests per minute per key (HTTP 429 with Retry-After).
- Webhooks are signed with HMAC-SHA256 (`X-Preflight-Signature: sha256=…`) and every
  delivery's status and latency is logged.

## Evaluation

`data/eval/claims.jsonl` holds 150 hand-written PayWise claims: 45 supported, 20 outdated,
35 contradicted, 35 unsupported, 15 needs_review, each tied to the fact that decides it.
`python -m app.eval.run` runs the real ledger on each and stores an `EvalRun`; the app
precomputes one at boot and shows it on the Evaluation page.

| Verdict | Precision | Recall | F1 | n |
|---|---|---|---|---|
| supported | 1.00 | 0.93 | 0.97 | 45 |
| outdated | 1.00 | 1.00 | 1.00 | 20 |
| contradicted | 0.94 | 0.94 | 0.94 | 35 |
| unsupported | 0.85 | 0.94 | 0.89 | 35 |
| needs_review | 0.71 | 0.67 | 0.69 | 15 |

Accuracy 0.92, macro recall 0.90 (plan target ≥ 0.85, met), problem-claim recall 1.00
(every claim that must not be published unchanged is flagged), `unsupported` precision 0.85
(plan target 0.90, not met). Failure analysis: five misses are vague claims labelled
needs_review that the ledger calls unsupported (shown in "Needs a human look" in the app);
two are claims about a different product or store whose numbers clash ("10% cashback on
UPI", "4.8 on the Apple App Store"); three are true paraphrases the small NLI model would not
entail. Caveat: the topical-similarity thresholds were calibrated on this same set; a
held-out split is planned.

## Running in 512 MB

Both models are int8 ONNX files run by ONNX Runtime (no PyTorch). Each was measured inside a
container capped at 512 MiB and 0.1 CPU, Render's free plan:

| Stage | Resident memory |
|---|---|
| App imported | 108 MiB |
| + bge-small int8 embedder | 223 MiB |
| + NLI int8 session and SentencePiece | 345 MiB |
| Full boot + demo history + a LinkedIn review | **362 MiB peak**, no OOM |

What made it fit (`app/ml/onnx.py`, `app/ml/nli.py`): graph optimisation off (it expanded the
int8 weights to 408 MiB at load; identical outputs without it), no memory arena, one thread;
SentencePiece instead of `tokenizers` for the 128k DeBERTa vocabulary (56 vs 106 MiB, identical
ids); `NLI_BATCH_SIZE=2` because DeBERTa's relative attention needs about 20 MiB per pair in
flight; one inference at a time; `MODEL_LOADING=lazy`; and the evaluation loaded from
`data/eval/precomputed_run.json` (`EVAL_AT_BOOT=precomputed`). Models are downloaded during
the build (`backend/scripts/fetch_models.py`) and used with `HF_HUB_OFFLINE=1`. If a model
fails to load, the Claim Ledger falls back to numeric and lexical checks and every
deterministic checker still runs.

## Testing

112 backend tests (pytest, a real Postgres per test with rollback), Playwright end-to-end
tests for the golden path and every page, and CI (ruff, mypy --strict, pytest, eslint, tsc,
production build) on every push.
