# Changes from the Round 1 plan

Each change from the Round 1 plan, with the reason. Kept short and honest.

| Area | Round 1 plan | Round 2 build | Why |
|---|---|---|---|
| Demo users | Three roles plus admin | Added a seeded **Reviewer** (abhi2) alongside Creator, Brand Manager, Approver and Admin | The permission table has a Reviewer column; a seeded reviewer lets judges see the "Needs a human look" queue |
| Demo user names | Riya Sharma, Arjun Mehta, Neha Iyer, Admin | **abhi1** (Creator), **abhi2** (Reviewer), **abhi3** (Brand Manager), **abhi4** (Approver), **abhi5** (Admin) | The author's preference: neutral demo identities |
| Frontend framework version | Next.js 14+ | Next.js 15.5 | The 15.1 template had published security advisories |
| Claim rules | CLM-01, 04, 06, 08 | Added **CLM-02** (contradicts an approved fact, critical), **CLM-03** (uses a superseded fact, major) and **CLM-05** (factual claim with no approved fact, major) | Every finding must cite a rule; the plan's verdicts `contradicted`, `outdated` and `unsupported` had no rule to cite |
| NLI model | DeBERTa-v3 NLI | `cross-encoder/nli-deberta-v3-xsmall` (22M params) | Fits comfortably in free CPU hosting with fast warm-up |
| Verdict logic | NLI entailment ≥ 0.7 decides `supported` | Same, plus a **deterministic support path**: if NLI is inconclusive but the numbers match exactly (or a verbatim quote covers most of the claim) on a clearly on-topic fact with no contradiction, the claim is `supported` at confidence 0.75 | The small NLI model rejects true paraphrases that add harmless detail ("…on your purchases"). The path never involves the LLM, keeps the quote check, and is visible in "How this verdict was reached" |
| Thresholds | Not specified | Topical-similarity gates for contradictions (numeric ≥ 0.74, NLI-only ≥ 0.75) | Calibrated on the labelled set: without them the model "contradicted" claims with loosely related facts. Calibrated on the same set we report on (no held-out split yet), noted in TECHNICAL.md |
| Finding merge | De-duplicate overlapping spans, keep highest severity | Merge only when findings cite the same rule on overlapping text, or cover nearly the same span (IoU ≥ 0.8) with the same type | Otherwise CLM-01 and CLM-04 on "India's #1 and 100% secure" collapse into one, and the plan's scenario expects both |
| Brand Score | Open findings only | Open findings, excluding those waiting in "Needs a human look" (confidence < 0.6) | Uncertain findings should not cost points until a person confirms them |
| Suggestions | LLM writes every suggestion | Brand-approved fallback wording from the rule (`fallback` in rules.csv) is used first; the LLM writes only what the rulebook has no wording for. "Free" (CLM-08) gets no rewrite, because the right fix is the offer disclaimer DSC-01 suggests | Safer (approved wording), faster (one fewer LLM round-trip, keeps a full review under 10 s) and stops euphemisms like "free" → "complimentary" |
| LLM model | Not fixed | Gemini `gemini-3.5-flash-lite` | Older Gemini models are retired; flash-lite answers JSON in 3–6 s, inside the 8 s timeout |
| Background jobs | Redis + RQ workers | In-process worker threads (one per review, own event loop) | Demo scale needs no queue; threads keep CPU-bound NLI off the API's event loop. A job queue can replace `runner.start_review` without touching the engine |
| Live progress | WebSocket | Server-Sent Events (`/api/reviews/{id}/events`) with replay of earlier events | Progress is one-way; SSE is simpler, proxies well and reconnects by itself |
| Disputes | Disputed critical findings block approval | Same, but a disputed critical **can be submitted**: the approver then either overrides it with a written reason (shown on the receipt) or requests changes | The dispute is a question for the approver; blocking submission would leave it nowhere to go |
| Readability library | textstat | textstat 0.7.4 (pyphen syllables) | Newer textstat downloads the CMU dictionary through NLTK at runtime (22 s, needs network) |
| UI kit | shadcn/ui | Small hand-written Tailwind components (`components/ui.tsx`) on a warm paper theme | Fewer moving parts under deadline; same accessible patterns (native `<dialog>`, focus rings, tooltips on focus) |
| Diff viewer | react-diff-viewer | jsdiff word diff rendered inline | react-diff-viewer does not support React 19 |
| Python ML runtime | Single requirements file | `requirements-ml.txt` (PyTorch CPU, sentence-transformers) installed only in the Docker image | CI never loads models, so it stays fast |
