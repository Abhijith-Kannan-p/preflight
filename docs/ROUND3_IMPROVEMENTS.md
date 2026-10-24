# Three major improvements for Round 3

Each builds directly on the Round 2 engine: the typed Finding contract, the Brand Knowledge
Base, the Claim Ledger, the AI gateway with masking, and the workflow with its audit log.

## 1. Visual and accessibility review

**What it is.** Images, PDF pages and HTML emails are checked like text: colours against the
brand palette, logo misuse, fonts, WCAG 2.2 contrast, missing alt text, and the words inside
images.

**Why it matters.** A large share of off-brand content is visual: a banner in the wrong teal,
a stretched logo, a social card whose "100% secure" headline is part of the image and so
escapes every text check today. Inaccessible contrast is also a legal and reputational risk.

**Technical approach.**
- Palette compliance: k-means colour extraction (k ≈ 6) per asset, then CIEDE2000 distance to
  the nearest brand colour; ΔE00 above a per-colour tolerance becomes a finding.
- Logo misuse: template matching (OpenCV, multi-scale) to find the logo, then aspect-ratio
  distortion, rotation and clear-space checks against the brand book's minimums.
- Contrast: WCAG 2.2 contrast ratio for text regions found by OCR bounding boxes.
- Alt text and HTML emails: parse `<img>` alt attributes and inline styles.
- OCR (Tesseract or PaddleOCR, local) turns text in images and scanned PDFs into normalised
  blocks, so it flows through the existing Claim Ledger and checkers unchanged.

**Reuses.** Normaliser (new block type with a bounding box), Finding contract (span gains an
optional box), Rulebook (new `visual` rule category with palette and logo configs), Review
workspace (highlight boxes over an image preview), Brand Score and receipts as-is.

**Success measures.** Palette and contrast precision ≥ 0.9 on a labelled set of 100 brand and
off-brand assets; OCR word error rate < 5 % on social cards; median review time for an image
< 6 s; the Round 2 golden path extended to a PDF flyer.

## 2. Governance intelligence

**What it is.** Three views that turn review history into guidance:
- **Guideline Health:** rules with high dispute or override rates are flagged as ambiguous,
  with an LLM-drafted rewording for the brand manager to accept or reject.
- **Stale-Content Radar:** when a fact is superseded, list every already-approved item whose
  Claim Ledger relied on the old fact, and offer a one-click re-check.
- **Creator Coach:** a per-author profile of recurring findings, with short tips shown on the
  New review page before the next draft.

**Why it matters.** Brand governance fails quietly: rules nobody understands get disputed
forever, approved content keeps quoting old numbers after a fact changes (exactly the F-086 →
F-087 case), and the same people repeat the same mistakes. Round 2 already records the data
needed to fix all three.

**Technical approach.** Guideline Health: per-rule dispute and override rates with a Wilson
lower bound to avoid noise from small counts; rewording proposals go through the AI gateway
(masked) and the normal versioned rule edit. Stale-Content Radar: the `claims` table already
stores the `fact_id` behind every verdict; a supersede event queries approved submissions
whose final revision cites the old fact. Creator Coach: aggregate findings by author and rule
over a rolling 60 days, with tips drawn from each rule's description and fallback wording.

**Reuses.** Insights API and charts, decisions and audit events (dispute and override data),
the Claim Ledger table, the supersede flow, notifications, and the re-check workflow.

**Success measures.** Rules flagged by Guideline Health and reworded show a ≥ 30 % drop in
dispute rate over the next 50 reviews; 100 % of approved items citing a superseded fact are
listed within a minute of the change; repeat findings per author fall by ≥ 25 % after four
weeks with Coach tips.

## 3. Brand Autopilot

**What it is.** Onboarding without hand-writing rules:
- **Rulebook Compiler:** upload a brand-book PDF; Preflight drafts typed rules (category,
  severity, patterns, page references) and approved facts for a brand manager to approve.
- **Voice Fingerprint:** learn the tone targets from a set of approved past content instead
  of hand-set numbers.
- **Local privacy mode:** run claim extraction, tone and suggestions on a local model
  (Ollama) so confidential brands make no external AI calls at all.

**Why it matters.** Today a brand team must type its rules in. Most already have a brand-book
PDF and years of approved posts. Some cannot send drafts to any hosted model.

**Technical approach.** Compiler: PyMuPDF layout extraction, section chunking, LLM extraction
constrained to the existing `RuleIn` / `FactIn` Pydantic schemas with page numbers kept;
every draft rule lands as `status=draft` and needs human approval (no rule goes live
unreviewed). Voice Fingerprint: score 50–200 approved items with the tone checker, take
robust per-trait means and spreads as targets and thresholds, and show the brand manager the
before/after profile. Local mode: an `OllamaProvider` behind the existing gateway interface
(`complete_json`), selected by `LLM_PROVIDER=ollama`, with the same validation and fallbacks.

**Reuses.** AI gateway, masking, schemas and validation, versioned rules and facts, tone
checker, settings page, audit log for every approval.

**Success measures.** On three public brand books, ≥ 80 % of compiled rules accepted without
edits and ≥ 90 % carry a correct page reference; a learned voice profile reduces tone
disputes by ≥ 30 % against hand-set targets; local mode passes the full test suite and the
evaluation set within 3 points of hosted-mode accuracy.
