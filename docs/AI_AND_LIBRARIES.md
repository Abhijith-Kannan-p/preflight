# AI tools, models and libraries

This file is updated as the build progresses. Everything listed here is used in the
submitted product or in building it.

## AI coding assistance

- **Claude Code (Anthropic)** was used as an AI pair-programmer throughout the build
  (scaffolding, code, tests and documentation drafts). All commits were reviewed and
  made by the author.

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
| pytest, pytest-asyncio, httpx | Tests | MIT / Apache-2.0 / BSD |
| ruff, mypy | Lint, format, type check | MIT |

## Frontend libraries

| Library | Purpose | License |
|---|---|---|
| Next.js 15, React 19 | Web app | MIT |
| Tailwind CSS 3 | Styling | MIT |
| Inter (Google Fonts via next/font) | Typeface | OFL |

## Infrastructure

| Component | Purpose |
|---|---|
| PostgreSQL 16 + pgvector (Docker image `pgvector/pgvector:pg16`) | Database and vector search |
| GitHub Actions | CI |
