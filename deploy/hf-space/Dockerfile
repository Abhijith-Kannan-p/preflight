# Preflight backend for a Hugging Face Docker Space (CPU basic, 16 GB RAM).
# Build context: the Space repo root, which deploy/push_space.sh fills with backend/ and data/.
FROM python:3.11-slim

# Spaces run the container as uid 1000.
RUN useradd -m -u 1000 user
ENV HOME=/home/user \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/home/user/.cache/huggingface \
    FASTEMBED_CACHE_PATH=/home/user/.cache/fastembed \
    DATA_DIR=/app/data \
    PORT=7860

WORKDIR /app
COPY backend/requirements-ml.txt backend/requirements.txt ./
RUN pip install -r requirements-ml.txt && pip install -r requirements.txt

COPY --chown=user backend/ /app/
COPY --chown=user data/ /app/data/

# Bake both local models into the image, so start-up never depends on huggingface.co.
USER user
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5'); \
from sentence_transformers import CrossEncoder; CrossEncoder('cross-encoder/nli-deberta-v3-xsmall')"
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1

EXPOSE 7860
CMD ["sh", "start.sh"]
