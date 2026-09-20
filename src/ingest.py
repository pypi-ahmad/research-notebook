"""Persist uploaded sources and index their chunks in embedded Qdrant."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path

from src.pack import (
    delete_source_points,
    get_source_point_counts,
    index_sources_to_qdrant,
)
from src.pdf_engine import process_pdf_document

SOURCES_DIR = Path("data/sources")


@dataclass(frozen=True)
class StoredSource:
    """Persisted source record used by the active application.

    Attributes:
        id: UUID string used by source files and Qdrant payloads.
        title: Source display title.
        text: Pasted or extracted source text.
        origin: Source origin, such as ``paste`` or ``upload``.
        pdf_type: Optional ``pdf-inspector`` classification for PDF uploads.
        route: Optional extraction route, ``native`` or ``ollama``.
    """
    id: str
    title: str
    text: str
    origin: str
    pdf_type: str | None = None
    route: str | None = None

    @property
    def content(self) -> str:
        return self.text

    @property
    def source_type(self) -> str:
        return self.origin

    @property
    def char_count(self) -> int:
        return len(self.text)

    @property
    def est_tokens(self) -> int:
        return self.char_count // 4


@dataclass(frozen=True)
class IngestResult:
    """Result returned after a source is persisted and indexed.

    Attributes:
        source: Stored source record.
        point_count: Number of Qdrant points upserted for the source.
        warnings: Non-fatal extraction or OCR warnings.
    """
    source: StoredSource
    point_count: int
    warnings: tuple[str, ...] = ()


class PdfIngestSkipped(ValueError):
    """Signal that a PDF had no ingestible native or OCR text.

    Attributes:
        warnings: Extraction and OCR warnings shown to the user.
        pdf_type: ``pdf-inspector`` classification that selected the route.
        route: Attempted extraction route.
    """

    def __init__(self, warnings: tuple[str, ...], pdf_type: str, route: str) -> None:
        super().__init__("PDF contained no extractable text; upload skipped.")
        self.warnings = warnings
        self.pdf_type = pdf_type
        self.route = route


def _source_path(source_id: str, sources_dir: Path = SOURCES_DIR) -> Path:
    return sources_dir / f"{uuid.UUID(source_id)}.json"


def _write_source(source: StoredSource, sources_dir: Path) -> Path:
    sources_dir.mkdir(parents=True, exist_ok=True)
    path = _source_path(source.id, sources_dir)
    payload = {
        "id": source.id,
        "title": source.title,
        "text": source.text,
        "origin": source.origin,
    }
    if source.pdf_type is not None:
        payload["pdf_type"] = source.pdf_type
    if source.route is not None:
        payload["route"] = source.route
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)
    return path


def ingest_text(
    title: str,
    text: str,
    origin: str = "paste",
    *,
    sources_dir: Path = SOURCES_DIR,
    qdrant_path: str = "data/qdrant",
    pdf_type: str | None = None,
    route: str | None = None,
) -> IngestResult:
    """Persist text as one source JSON record and upsert its chunks.

    Args:
        title: Source display title.
        text: Non-empty text to persist.
        origin: Source origin label.
        sources_dir: Directory for individual source JSON files.
        qdrant_path: Embedded Qdrant storage path.
        pdf_type: Optional PDF classification retained with PDF uploads.
        route: Optional PDF extraction route retained with PDF uploads.

    Returns:
        Persisted source, Qdrant point count, and no extraction warnings.

    Raises:
        ValueError: If the text is empty.
        RuntimeError: If embedded Qdrant is locked by another process.
    """
    clean_text = text.strip()
    if not clean_text:
        raise ValueError("Source text is empty.")
    source = StoredSource(
        id=str(uuid.uuid4()),
        title=title.strip() or "Untitled source",
        text=clean_text,
        origin=origin,
        pdf_type=pdf_type,
        route=route,
    )
    path = _write_source(source, sources_dir)
    try:
        point_count = index_sources_to_qdrant([source], qdrant_path=qdrant_path)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return IngestResult(source=source, point_count=point_count)


def ingest_upload(
    file_bytes: bytes,
    filename: str,
    title: str | None = None,
    *,
    force_ocr: bool = False,
    sources_dir: Path = SOURCES_DIR,
    qdrant_path: str = "data/qdrant",
) -> IngestResult:
    """Extract a supported upload, persist it, and upsert its chunks.

    Args:
        file_bytes: Raw PDF, TXT, or Markdown upload bytes.
        filename: Original filename used to select extraction.
        title: Optional display title; defaults to ``filename``.
        force_ocr: Route all PDF pages through optional Ollama OCR.
        sources_dir: Directory for individual source JSON files.
        qdrant_path: Embedded Qdrant storage path.

    Returns:
        Persisted source, Qdrant point count, and extraction warnings.

    Raises:
        PdfIngestSkipped: If a PDF route yields no ingestible text.
        ValueError: If the file extension is unsupported.
        RuntimeError: If embedded Qdrant is locked by another process.
    """
    suffix = Path(filename).suffix.casefold()
    warnings: tuple[str, ...] = ()
    pdf_type: str | None = None
    route: str | None = None
    if suffix == ".pdf":
        pdf_result = process_pdf_document(file_bytes, filename, force_ocr=force_ocr)
        text = pdf_result.markdown
        warnings = tuple(pdf_result.warnings)
        pdf_type = pdf_result.pdf_type
        route = pdf_result.route
        if not text.strip():
            raise PdfIngestSkipped(
                warnings
                or ("PDF contained no extractable text; upload skipped.",),
                pdf_type,
                route,
            )
    elif suffix in {".txt", ".md"}:
        try:
            text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text = file_bytes.decode("latin-1")
    else:
        raise ValueError("Only PDF, TXT, and Markdown files are supported.")

    result = ingest_text(
        title or filename,
        text,
        origin="upload",
        sources_dir=sources_dir,
        qdrant_path=qdrant_path,
        pdf_type=pdf_type,
        route=route,
    )
    return IngestResult(result.source, result.point_count, warnings)


def load_sources(sources_dir: Path = SOURCES_DIR) -> list[StoredSource]:
    """Load valid individual source JSON records from a directory.

    Args:
        sources_dir: Directory containing ``<source_id>.json`` records.

    Returns:
        Parsed sources ordered by filename; malformed records are skipped.
    """
    if not sources_dir.exists():
        return []
    sources: list[StoredSource] = []
    for path in sorted(sources_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            sources.append(
                StoredSource(
                    id=data["id"],
                    title=data["title"],
                    text=data["text"],
                    origin=data["origin"],
                    pdf_type=data.get("pdf_type"),
                    route=data.get("route"),
                )
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
    return sources


def delete_source(
    source_id: str,
    *,
    sources_dir: Path = SOURCES_DIR,
    qdrant_path: str = "data/qdrant",
) -> int:
    """Delete a source JSON record and its associated Qdrant points.

    Args:
        source_id: UUID of the source to delete.
        sources_dir: Directory containing individual source JSON files.
        qdrant_path: Embedded Qdrant storage path.

    Returns:
        Number of Qdrant points deleted.

    Raises:
        RuntimeError: If embedded Qdrant is locked by another process.
    """
    point_count = delete_source_points(source_id, qdrant_path=qdrant_path)
    _source_path(source_id, sources_dir).unlink(missing_ok=True)
    return point_count


__all__ = [
    "IngestResult",
    "PdfIngestSkipped",
    "StoredSource",
    "delete_source",
    "get_source_point_counts",
    "ingest_text",
    "ingest_upload",
    "load_sources",
]
