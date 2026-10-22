.PHONY: up down test lint

up:
	docker compose up --build

down:
	docker compose down

test:
	cd backend && pytest -q

lint:
	cd backend && ruff check . && ruff format --check . && mypy app
	cd frontend && npm run lint && npm run typecheck
