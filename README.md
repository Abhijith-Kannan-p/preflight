# Preflight

[![CI](https://github.com/Abhijith-Kannan-p/preflight/actions/workflows/ci.yml/badge.svg)](https://github.com/Abhijith-Kannan-p/preflight/actions/workflows/ci.yml)

**Content cleared before it goes live.** Preflight is a review gate that sits before
publication. It holds a brand book as versioned rules, checks every draft against those
rules and a registry of approved facts, and returns cited, explainable findings with
suggestions that keep the author's intent. People approve; the AI never does.

Built for CodeAxis Round 2 by team **kabhijith447**.

## Local setup

```bash
cp .env.example .env    # optional: add an LLM key; works without one
docker compose up --build
```

- Frontend: http://localhost:3000
- API: http://localhost:8000 (OpenAPI docs at `/docs`, health at `/health`)

## License

MIT
