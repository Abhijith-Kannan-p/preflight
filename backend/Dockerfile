# Build context is the repository root (backend code + data/ seed files).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/.cache/huggingface \
    FASTEMBED_CACHE_PATH=/app/.cache/fastembed \
    DATA_DIR=/app/data

WORKDIR /app

COPY backend/requirements-ml.txt .
RUN pip install -r requirements-ml.txt
COPY backend/requirements.txt .
RUN pip install -r requirements.txt

COPY backend/ .
COPY data/ /app/data/

# Hugging Face Spaces expects port 7860; docker compose overrides PORT.
ENV PORT=7860
EXPOSE 7860

CMD ["sh", "start.sh"]
