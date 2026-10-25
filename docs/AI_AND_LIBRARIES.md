# AI tools, models and libraries

This file is updated as the build progresses. Everything listed here is used in the
submitted product or in building it.

## AI coding assistance

- **Claude Code (Anthropic)** was used as an AI pair-programmer throughout the build
  (scaffolding, code, tests and documentation drafts). All commits were reviewed and
  made by the author.

## Models

| Model | Where it runs | Purpose | License |
|---|---|---|---|
| `BAAI/bge-small-en-v1.5`, int8 ONNX export `Xenova/bge-small-en-v1.5` (`onnx/model_quantized.onnx`) | Locally on the backend CPU (ONNX Runtime) | 384-d embeddings for dense fact retrieval and semantic-drift scores | MIT |
| `cross-encoder/nli-deberta-v3-xsmall`, official int8 ONNX export (`onnx/model_quint8_avx2.onnx`) | Locally on the backend CPU (ONNX Runtime + SentencePiece) | Natural-language inference (fact ⇒ claim) in the Claim Ledger | Apache-2.0 |
| Google Gemini `gemini-3.5-flash-lite` (Gemini API) | Google, via HTTPS, **after masking** | Claim extraction (proposals only), tone scoring, suggestion wording where the rulebook has none | Google API terms |
| Groq-hosted model (optional, `LLM_PROVIDER=groq`) | Groq, via HTTPS, after masking | Same as Gemini; alternative provider | Groq API terms |

The hosted LLM never decides whether a claim is true. Verdicts come from retrieval, the local
NLI model and exact numeric comparison. Every LLM call is logged (provider, model, latency,
tokens, how many values were masked) and summarised in the "AI used in this review" panel.
With `LLM_PROVIDER=none` the product runs fully offline in deterministic mode.

## Data

All brand data (PayWise rules, facts, terms, channels, confidential terms, sample
drafts) is fictional and was written for this project. It lives in `data/seed/`.

## Backend libraries

| Library | Purpose | License |
|---|---|---|
| FastAPI | HTTP API, OpenAPI docs | MIT |
| Uvicorn | ASGI server | BSD-3 |
| Pydantic v2, pydantic-settings | Schemas, validation, configuration | MIT |
| SQLAlchemy 2 | ORM | MIT |
| psycopg 3 | PostgreSQL driver | LGPL-3.0 |
| Alembic | Database migrations | MIT |
| pgvector (Python) | Vector column type | MIT |
| NumPy | Vector maths | BSD-3 |
| python-multipart | File uploads | Apache-2.0 |
| python-docx | DOCX intake and sample generation | MIT |
| PyMuPDF | PDF text extraction | AGPL-3.0 (used unmodified; source of this project is public) |
| rapidfuzz | Fuzzy product-name matching | MIT |
| textstat | Flesch Reading Ease | MIT |
| reportlab | Sample PDF and Review Receipt PDF | BSD |
| rank-bm25 | Lexical (BM25) fact retrieval | Apache-2.0 |
| ONNX Runtime | Runs both quantised models | MIT |
| tokenizers (Hugging Face) | bge-small tokenisation | Apache-2.0 |
| sentencepiece | DeBERTa-v3 tokenisation (lower memory than tokenizers) | Apache-2.0 |
| huggingface-hub | Downloads model files at build time | Apache-2.0 |
| PyTorch (CPU), sentence-transformers | Optional NLI backend (`NLI_BACKEND=torch`) | BSD-3 / Apache-2.0 |
| httpx | Async HTTP client for LLM providers | BSD-3 |
| pytest, pytest-asyncio, httpx | Tests | MIT / Apache-2.0 / BSD |
| ruff, mypy | Lint, format, type check | MIT |

## Frontend libraries

| Library | Purpose | License |
|---|---|---|
| Next.js 15, React 19 | Web app | MIT |
| Tailwind CSS 3 | Styling | MIT |
| Inter (Google Fonts via next/font) | Typeface | OFL |
| framer-motion | Splash, perspective-tunnel hero, gauge and tour animation | MIT |
| lucide-react | Icons | ISC |
| SWR | Data fetching and cache revalidation | MIT |
| jsdiff (`diff`) | Word-level revision diff | BSD-3 |
| Recharts | Insights and evaluation charts | MIT |
| clsx | Class name composition | MIT |
| Playwright | Golden-path end-to-end test | Apache-2.0 |

## Templates and design inspiration

- The landing hero's perspective-tunnel motion was adapted from a "Perspective Tunnel
  Hero" component snippet (framer-motion) shared by the author. It was rewritten to fly
  Preflight finding cards instead of photos and to follow normal page scroll.
- No UI kit or page template was copied; components are hand-written with Tailwind.

## Infrastructure

| Component | Purpose |
|---|---|
| PostgreSQL 16 + pgvector (Docker image `pgvector/pgvector:pg16`) | Database and vector search |
| GitHub Actions | CI |
