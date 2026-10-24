.PHONY: up down migrate seed test lint

up:
	docker compose up --build

down:
	docker compose down

migrate:
	cd backend && alembic upgrade head

seed:
	cd backend && python -m app.seed

test:
	cd backend && pytest -q

lint:
	cd backend && ruff check . && ruff format --check . && mypy app
	cd frontend && npm run lint && npm run typecheck
