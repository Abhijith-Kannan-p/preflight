# Preflight backend for a Hugging Face Docker Space (CPU basic).
# Build context: the Space repo root, which deploy/push_space.sh fills with backend/ and data/.
FROM python:3.11-slim

# Spaces run the container as uid 1000.
RUN useradd -m -u 1000 user
ENV HOME=/home/user \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/home/user/.cache/huggingface \
    DATA_DIR=/app/data \
    PORT=7860

WORKDIR /app
COPY backend/requirements.txt backend/requirements-ocr.txt ./
RUN pip install -r requirements.txt && pip install --no-deps -r requirements-ocr.txt

COPY --chown=user backend/ /app/
COPY --chown=user data/ /app/data/

# Bake both quantised ONNX models into the image, so start-up never depends on huggingface.co.
USER user
RUN python /app/scripts/fetch_models.py
ENV HF_HUB_OFFLINE=1

EXPOSE 7860
CMD ["sh", "start.sh"]
