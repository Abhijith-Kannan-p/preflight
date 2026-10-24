#!/bin/sh
# Container entry point: migrate, seed an empty database, then serve.
set -e

alembic upgrade head
python -m app.seed --if-empty
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-7860}" --proxy-headers
