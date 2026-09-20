"""Optional Ollama health and OCR helpers."""

from __future__ import annotations

from ollama import Client

from src.config import OLLAMA_HOST
from src.pdf_engine import PdfExtractionResult, process_pdf_document


def list_ollama_tags() -> list[str]:
    """Return sorted model tags from the configured local Ollama service.

    Returns:
        Installed model names with empty entries removed.

    Raises:
        Exception: Propagates an Ollama connection or API error to the caller.
    """
    response = Client(host=OLLAMA_HOST, timeout=3.0).list()
    return sorted(model.model for model in response.models if model.model)


__all__ = ["PdfExtractionResult", "list_ollama_tags", "process_pdf_document"]
