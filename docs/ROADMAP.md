# Roadmap

Where Preflight goes after the competition, in the order a real brand team would need it. Each
item says why it matters, what it depends on, and how we would know it worked. Items are
grounded in what the Round 3 build measured (see [TESTING.md](TESTING.md)), not wishes.

## Next 3 months: from demo to a pilot with one real brand

| Item | Why | Depends on | Done when |
|---|---|---|---|
| **Real accounts and SSO** (Google Workspace and Microsoft Entra via OIDC; invite links; roles per workspace) | The demo role switcher is not access control. A pilot brand needs its own people, signed in with the identity provider they already use, and an audit trail that names them | Workspaces and roles already exist per sandbox; replace demo tokens with OIDC sessions; per-workspace invitations | A pilot team signs in with SSO; every audit event names a real person |
| **Own brand onboarding with the Rulebook Compiler** | The compiler was measured on one brand book we wrote (recall 94%, 100% acceptable without edits). A real book has columns, images of tables and vaguer prose | Real accounts; PDF layout handling for multi-column pages; OCR of table images (RapidOCR is already in the stack) | On the pilot's own book, at least 80% of candidates are accepted without edits, measured from their decisions |
| **Claim precision on unseen claims** | `unsupported` precision is 0.94 on the tuning set but 0.67 on held-out claims | A larger held-out set written by people other than the developer; hedged-wording detection learned from labelled examples instead of a word list | ≥ 0.85 on a fresh held-out set that was never used for tuning |
| **Faster reviews on small hosts** | A full off-brand review takes 28 s on Render's 0.1 CPU (target 20 s) | One paid instance (1 CPU: about 1–2 s for NLI) or batching NLI across claims; LLM calls in parallel with the NLI | 95th percentile under 20 s; first findings under 3 s |
| **Webhook hardening** | Webhook URLs are not checked against private addresses | Resolve the host and refuse private, loopback and link-local ranges; per-workspace allow-list | Requests to private ranges are refused with a clear message |

## 3 to 6 months: where content is written

| Item | Why | Depends on | Done when |
|---|---|---|---|
| **WordPress plugin** | Most marketing copy is published from a CMS; the public API and `examples/cms_hook.py` already support a pre-publish gate | API keys and the `blocking` flag (built); a plugin that calls them on "Publish" and shows findings in the editor sidebar | A WordPress post with a critical finding cannot be published without an override reason |
| **Google Docs add-on** | Drafts are written and reviewed in Docs before they reach a CMS | Real accounts; margin notes mapped to Docs comments using the exact character offsets the engine already returns | Findings appear as Docs comments on the right words; accepting one applies the suggestion |
| **Figma plugin** | Visual review today needs an export; designers work in Figma | The visual pipeline (OCR, palette, contrast, logo) on a frame export through the API | A designer checks a frame without leaving Figma; VIS and ACC findings point at the layer |
| **Team analytics** | Guideline Health, the Radar and the Coach show per-rule and per-writer signals; managers also need trends by team, channel and agency | Teams as a first-class grouping; the existing Insights queries extended | A brand manager compares agencies by repeat-mistake rate and time to clearance |
| **Coach measured on real writers** | The repeat-mistake target (25% fewer) could not be tested on seeded history | A pilot with writers who see the Coach before writing | A measured before/after on the pilot's own drafts |

## 6 to 12 months: wider reach and regulated brands

| Item | Why | Depends on | Done when |
|---|---|---|---|
| **Indian languages** (Hindi first, then Tamil, Bengali and Marathi) | PayWise-like brands publish in several languages; today Hindi text is accepted but not checked for claims or tone | Multilingual embeddings and NLI (or translation to English with alignment back to the original offsets); terminology and disclaimers per language; labelled sets per language | Claim Ledger and terminology checks reach the English evaluation figures on a labelled Hindi set |
| **Local-model mode for regulated brands** | Banks and insurers often cannot send drafts to a hosted LLM even after masking. (Planned for Round 3 and dropped by agreement.) | An Ollama or vLLM provider behind the existing gateway interface (`complete_json`); a host with a GPU or a large CPU | The full test suite passes with no external AI calls; evaluation within 3 points of hosted mode |
| **Video and audio** | Brand claims increasingly appear in short videos and podcasts | Speech-to-text with timestamps; key-frame OCR with the existing visual pipeline; findings anchored to time ranges | A 60-second video's spoken and on-screen claims are checked with timestamps |
| **Approval chains and SLAs** | Larger teams need legal and compliance sign-off after brand approval | The workflow state machine generalised to configurable steps | A draft passes brand, then legal, with each step on the certificate |
| **Fact registry integrations** | Approved facts live in other systems (product catalogues, pricing tables, policy documents) | Connectors that create supersession events, which the Stale-Content Radar already handles | A price change in the source system flags every cleared post that quoted it within a minute |

## Not planned

- Auto-publishing or auto-approving content: people approve, and that stays the product's
  core promise.
- Generating marketing copy from scratch: Preflight checks and suggests minimal, intent-keeping
  edits; it is not a writing tool.
