"""Download the local models at build time so the running service never fetches them.

Usage (from the repo root, in a build step): python backend/scripts/fetch_models.py
Respects HF_HOME, so the files land where the service reads them.
"""

import os
import sys
from pathlib import Path

# The service runs with HF_HUB_OFFLINE=1; the build step must be allowed to download.
os.environ["HF_HUB_OFFLINE"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> None:
    from huggingface_hub import hf_hub_download

    from app.config import get_settings

    settings = get_settings()
    for filename in (settings.embedding_onnx_file, "tokenizer.json"):
        hf_hub_download(settings.embedding_onnx_repo, filename)
    print("embedding model ready:", settings.embedding_onnx_repo, settings.embedding_onnx_file)
    for filename in (settings.nli_onnx_file, "spm.model", "config.json"):
        hf_hub_download(settings.nli_model, filename)
    print("NLI model ready:", settings.nli_model, settings.nli_onnx_file)


if __name__ == "__main__":
    main()
