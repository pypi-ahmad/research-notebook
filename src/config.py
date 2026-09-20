"""Application constants and environment-presence helpers."""

from __future__ import annotations

import os

AGNES_BASE_URL = "https://apihub.agnes-ai.com/v1"
AGNES_MODEL = "agnes-3.0-flash"
QDRANT_PATH = "data/qdrant"
QDRANT_COLLECTION = "sources"
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_OCR_MODEL = os.environ.get("OLLAMA_OCR_MODEL", "AuditAid/PaddleOCR-VL-1.6-0.9B")


def agnes_key_is_set() -> bool:
    """Return Agnes key presence without exposing the secret value.

    Returns:
        ``True`` when ``AGNESAI_API_KEY`` is available to this process.
    """
    return bool(os.environ.get("AGNESAI_API_KEY"))
