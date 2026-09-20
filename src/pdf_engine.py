"""PDF extraction through pdf-inspector with optional local Ollama OCR."""

from __future__ import annotations

import base64
import os
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import pdf_inspector
import pypdfium2 as pdfium

from src.config import OLLAMA_HOST, OLLAMA_OCR_MODEL

DEFAULT_PAGES_DIR = Path("data/pages")
DEFAULT_OLLAMA_HOST = OLLAMA_HOST
DEFAULT_OLLAMA_MODEL = OLLAMA_OCR_MODEL


@dataclass
class PdfExtractionResult:
    """Extracted local PDF content and OCR-routing diagnostics.

    Attributes:
        pdf_type: Classification returned by ``pdf-inspector``.
        route: Extraction route, ``native`` or ``ollama``.
        confidence: Inspector confidence score.
        page_count: Number of PDF pages.
        markdown: Native and optional OCR Markdown content.
        pages_routed_to_ollama: Pages that produced OCR text.
        warnings: Non-fatal inspection or OCR warnings.
    """
    pdf_type: str
    route: str
    confidence: float
    page_count: int
    markdown: str
    pages_routed_to_ollama: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _ollama_settings() -> tuple[str, str]:
    host = os.environ.get("OLLAMA_HOST", DEFAULT_OLLAMA_HOST).rstrip("/")
    if not host.startswith(("http://", "https://")):
        host = f"http://{host}"
    model = os.environ.get("OLLAMA_OCR_MODEL", DEFAULT_OLLAMA_MODEL)
    return host, model


def _ollama_model_available(host: str, model: str) -> tuple[bool, str | None]:
    """Check Ollama and requested model without downloading or changing state."""
    try:
        response = httpx.post(f"{host}/api/show", json={"model": model}, timeout=3.0)
        if response.status_code == 404:
            return False, f"Ollama model '{model}' is not installed; skipped OCR pages."
        response.raise_for_status()
        return True, None
    except Exception as exc:
        return False, f"Ollama OCR is unavailable; skipped OCR pages. {exc}"


def _render_page(pdf_path: Path, page_number: int, output_path: Path) -> None:
    """Render one 1-indexed page to PNG with pypdfium2."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document = pdfium.PdfDocument(str(pdf_path))
    try:
        page = document[page_number - 1]
        try:
            page.render(scale=2.0).to_pil().save(output_path, format="PNG")
        finally:
            page.close()
    finally:
        document.close()


def _ocr_page(image_path: Path, host: str, model: str) -> str:
    image = base64.b64encode(image_path.read_bytes()).decode("ascii")
    response = httpx.post(
        f"{host}/api/generate",
        json={
            "model": model,
            "prompt": "OCR:",
            "images": [image],
            "stream": False,
        },
        timeout=180.0,
    )
    response.raise_for_status()
    return str(response.json().get("response", "")).strip()


def process_pdf_document(
    file_bytes: bytes, filename: str = "document.pdf", force_ocr: bool = False
) -> PdfExtractionResult:
    """Extract local PDF Markdown and optionally OCR routed pages.

    Args:
        file_bytes: Raw PDF bytes.
        filename: Original filename used to name temporary OCR page images.
        force_ocr: Whether to route every page through optional Ollama OCR.

    Returns:
        Native Markdown plus OCR content when available, route metadata, and
        non-fatal warnings for skipped or failed OCR pages.

    Notes:
        OCR is used only for a routed PDF and an available local Ollama model.
        The function never downloads a model or calls Firecrawl.
    """
    DEFAULT_PAGES_DIR.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            suffix=".pdf", dir=DEFAULT_PAGES_DIR, delete=False
        ) as temp_file:
            temp_file.write(file_bytes)
            temp_path = Path(temp_file.name)

        result = pdf_inspector.process_pdf(str(temp_path))
        pdf_type = result.pdf_type
        native_markdown = (result.markdown or "").strip()
        page_count = result.page_count
        warnings: list[str] = []

        if force_ocr or pdf_type in {"scanned", "image_based"} or not native_markdown:
            ocr_pages = list(range(1, page_count + 1))
        elif pdf_type == "mixed":
            ocr_pages = list(result.pages_needing_ocr)
        else:
            ocr_pages = []

        if not ocr_pages:
            return PdfExtractionResult(
                pdf_type=pdf_type,
                route="native",
                confidence=result.confidence,
                page_count=page_count,
                markdown=native_markdown,
            )

        host, model = _ollama_settings()
        available, warning = _ollama_model_available(host, model)
        if not available:
            if warning:
                warnings.append(warning)
            return PdfExtractionResult(
                pdf_type=pdf_type,
                route="ollama",
                confidence=result.confidence,
                page_count=page_count,
                markdown=native_markdown,
                warnings=warnings,
            )

        ocr_sections: list[str] = []
        routed_pages: list[int] = []
        document_id = uuid.uuid4().hex[:8]
        safe_stem = "".join(
            c if c.isalnum() or c in "-_" else "_" for c in Path(filename).stem
        )

        for page_number in ocr_pages:
            image_path = (
                DEFAULT_PAGES_DIR / f"{safe_stem}_{document_id}_page_{page_number}.png"
            )
            try:
                _render_page(temp_path, page_number, image_path)
                page_markdown = _ocr_page(image_path, host, model)
                if page_markdown:
                    routed_pages.append(page_number)
                    ocr_sections.append(
                        f"<!-- OCR page {page_number} -->\n{page_markdown}"
                    )
                else:
                    warnings.append(
                        f"Ollama returned no text for page {page_number}; page skipped."
                    )
            except Exception as exc:
                warnings.append(
                    f"OCR failed for page {page_number}; page skipped. {exc}"
                )

        markdown_parts = [part for part in [native_markdown, *ocr_sections] if part]
        return PdfExtractionResult(
            pdf_type=pdf_type,
            route="ollama",
            confidence=result.confidence,
            page_count=page_count,
            markdown="\n\n".join(markdown_parts),
            pages_routed_to_ollama=routed_pages,
            warnings=warnings,
        )
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def extract_text_from_pdf(file_bytes: bytes, filename: str = "document.pdf") -> str:
    """Return extracted PDF Markdown without route diagnostics.

    Args:
        file_bytes: Raw PDF bytes.
        filename: Original filename used for temporary OCR page names.

    Returns:
        Native and optional OCR Markdown text.
    """
    return process_pdf_document(file_bytes, filename).markdown
