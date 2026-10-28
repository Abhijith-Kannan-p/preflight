# Three major improvements for Round 3

Each builds directly on the Round 2 engine: the typed Finding contract, the Brand Knowledge
Base, the Claim Ledger, the AI gateway with masking, and the workflow with its audit log.

## 1. Visual and accessibility review (delivered)

**What it is.** Images (PNG, JPG, WebP), scanned PDFs and HTML emails are reviewed like any
draft: the text inside the image is read with OCR and goes through every text checker, and
four visual checks run on the pixels.

**Try it.** New review → "Festive banner (image)", "Scanned flyer (PDF)", "Email with images
(HTML)", "Stretched-logo post (image)" or "Clean visual (passes)". Then "Upload a new version"
with `data/seed/files/paywise_clean_visual.png` to see the fixes clear.

**What was built.**
- **Intake.** Images up to 5 MB (decompression-bomb guard at 40 MP); PDFs with less than 40
  text-layer characters per page are treated as scans and rasterised with PyMuPDF at 150 dpi
  (at most 5 pages). Pages are reduced to 1,400 px and stored with the revision (WebP).
  HTML emails: text by block element, every `<img>` with its `alt`, and CSS colours. DOCX:
  alt text of inline pictures.
- **OCR.** RapidOCR (PP-OCRv4 detection and recognition, ONNX Runtime; no Tesseract, no
  PyTorch). Lines are grouped into paragraph blocks with a per-line layout, so CLM, TRM, DSC
  and tone findings on image text are drawn on the image. Detection runs on a copy reduced
  to 736 px (960 px for scans): RapidOCR otherwise detects at full size, which cost +230 MiB.
  A small clean-up restores spaces OCR drops at letter-digit and punctuation boundaries and
  reads "1oo%" as "100%". The logo's own letters are removed from the copy.
- **VIS-01 palette.** Deterministic k-means (k = 6) on a 120 px thumbnail; each colour over
  8% of the image is compared with the brand palette by CIEDE2000 (our numpy implementation,
  tested against all of Sharma et al.'s reference pairs); ΔE00 over 10 from every brand colour
  is a finding with the colour's region. The palette is editable in Rulebook → Palette.
- **ACC-01 contrast.** For every OCR line: background = most common colour on the box edge,
  text = the pixels furthest from it; WCAG 2.2 ratio; 4.5:1, or 3:1 for large text (a line box
  at least 29 px tall at full size, i.e. 24 px type shown at 1x).
- **VIS-02 logo distortion.** OpenCV template matching over sizes and aspect ratios,
  coarse-to-fine, confirmed by brand-teal colour; the teal tile's own bounding box gives the
  aspect ratio to the pixel. Over 5% from 1:1 is a finding.
- **VIS-03 clear space.** The lockup (mark + "PayWise" wordmark found by OCR) needs a quarter
  of the logo height clear on every side; a median-filtered ring around it is checked for
  other content and other text. Implemented, not declared as a limitation.
- **ACC-02 / ACC-03 alt text.** Missing alt in HTML or DOCX (ACC-02); empty, file-name,
  "image of…" or one-word alt text, including the alt text the author types for an uploaded
  image (ACC-03).
- **UI.** The Visual Review desk: the page with a box per finding (and, on request, every OCR
  line and the logo with its clear-space ring), margin notes, the palette strip with ΔE to
  the nearest brand colour, a contrast table, and the OCR text as a proof sheet. The
  preflight checklist shows OCR, palette, contrast and logo as their own steps.

**Measured results vs targets.**

| Measure | Target | Result |
|---|---|---|
| Precision on 100 labelled assets | ≥ 0.90 | **1.00** (recall 0.99) |
| OCR words read correctly | (WER < 5%) | **98.3%** |
| Time per image, normal CPU | < 6 s | **1.3 s** median, 1.6 s p95 (whole visual review) |
| OCR per image on Render-like 0.1 CPU | < 6 s | **6.8 s** banner, 6.8–8.4 s other images; **11.3 s** for a scanned A4 page. Target missed on 0.1 CPU. |
| Peak memory on 512 MB / 0.1 CPU | < 450 MiB | **437 MiB** server high-water mark (OCR and NLI never loaded together) |

The labelled set is generated from our own templates with known injected issues (34 off-palette,
24 distorted logos, 27 crowded clear spaces, 26 low-contrast lines, 30 risky claims in the
image) plus four composed samples, so it measures the checks against ground truth but is easier
than real marketing images: photographs, unusual fonts and busy backgrounds will score lower.
The one miss is OCR gluing "securepayments", which hides "100% secure" from CLM-04.

**Limitations.** On Render's 0.1 CPU a whole visual review takes 25–30 s (the NLI model is
released during OCR and reloaded after). Remote images in HTML emails are not downloaded (their
alt text is checked; upload the image itself for a visual review). OCR sometimes glues two words
("onevery"). The public API accepts text documents only; images are reviewed in the web app.

## 2. Governance intelligence (delivered)

**Try it.** Governance (top menu) as abhi3 (Brand Manager). The seeded six-week history has
realistic disputes, overrides, a reworded rule and recurring mistakes, so every view has data
on first open.

**Guideline Health.** Per rule and per rule version: findings raised (once per review),
dispute, override and acceptance rates, and
`ambiguity = 0.6 × dispute rate + 0.4 × override rate` (shown from 4 findings, flagged at
30%). The board lists flagged rules with the writers' dispute reasons grouped by theme
(word-stem overlap). "Suggest clearer wording" sends the rule and those reasons to the hosted
LLM (masked) and returns a rewrite with a rationale; without the LLM a labelled deterministic
draft quotes the main objection. The brand manager edits it and publishes it as a new rule
version (audit-logged). Dispute rate is then compared per version.

**Stale-Content Radar.** A fact-dependency index from Claim Ledger evidence on cleared items:
item → cleared revision → claim → fact, with the fact's wording at review time. Facts that are
superseded, edited, retired or past their valid-until date list every item that relied on them:
the item, the exact sentence, old wording struck through, new wording, and "Re-check now", which
opens the cleared text as a new review against today's facts. Every fact edit, supersession and
retirement notifies the authors and brand managers in the same request. "Simulate fact update
on F-087" supersedes the settlement-time fact in the visitor's own workspace.

**Creator Coach.** Per author: recurring first-draft rules, trend, the repeat-mistake rate (a
first-draft finding on a rule that already flagged an earlier first draft of the same author,
divided by all first-draft findings; older half vs newer half of their drafts) and two or three
tips from the rule's guidance, the brand-approved wording and the author's own last fix. A
compact panel sits on the New review page before writing; the full Coach is on Governance.

**Measured results vs targets.**

| Measure | Target | Result |
|---|---|---|
| Disputes on reworded rules | 30% fewer | **DSC-01: 80% → 0% disputes per finding (−100%)** after v2 narrowed its triggers (seeded history: 5 findings on v1, 4 on v2, a small sample) |
| Affected approved items listed after a fact change | 100% within one minute | **100%** (test: 4 of 4 dependents, no false entries); listed **0.3 s** after the change locally |
| Repeat mistakes per author | 25% fewer | **Baseline measured, target not yet testable**: abhi1 42% (older half) → 100% (newer half, "repeating"); abhi3 0% → 50%. The seeded history has no Coach in it, so these are the "before" numbers; the target needs authors writing after seeing the Coach. |

**Limitations.** Coach tips are deterministic (the LLM tip option was cut per the agreed cut
order; the rulebook's wording proved specific enough). The repeat-mistake rate rises naturally
as an author's history grows (more earlier rules to repeat), so it should be compared over equal
spans. Version metrics on the seeded history are small samples.

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
