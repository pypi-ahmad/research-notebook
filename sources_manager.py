"""Sources management and context packing module.

Handles:
- Storing and loading sources from data/sources/sources.jsonl
- Extracting text from PDF, TXT, MD, and web URLs
- Packing sources against a character budget for Agnes 512K context window
- Calculating estimated token counts (chars / 4)
"""

from __future__ import annotations

import io
import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

DEFAULT_SOURCES_DIR = Path("data/sources")
DEFAULT_SOURCES_FILE = DEFAULT_SOURCES_DIR / "sources.jsonl"


@dataclass
class SourceItem:
    id: str
    title: str
    source_type: str  # "paste", "upload", "url"
    content: str
    char_count: int
    est_tokens: int
    created_at: str
    filename: Optional[str] = None
    url: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def ensure_storage_dir(sources_file: Path = DEFAULT_SOURCES_FILE) -> Path:
    """Ensure data/sources directory exists and return target JSONL path."""
    sources_file.parent.mkdir(parents=True, exist_ok=True)
    return sources_file


def load_sources(sources_file: Path = DEFAULT_SOURCES_FILE) -> List[SourceItem]:
    """Load all source items from the JSONL storage."""
    ensure_storage_dir(sources_file)
    if not sources_file.exists():
        return []

    items: List[SourceItem] = []
    with open(sources_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                items.append(
                    SourceItem(
                        id=data["id"],
                        title=data.get("title", "Untitled"),
                        source_type=data.get("source_type", "paste"),
                        content=data.get("content", ""),
                        char_count=data.get("char_count", len(data.get("content", ""))),
                        est_tokens=data.get("est_tokens", len(data.get("content", "")) // 4),
                        created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
                        filename=data.get("filename"),
                        url=data.get("url"),
                        metadata=data.get("metadata", {}),
                    )
                )
            except Exception:
                continue
    return items


def save_sources(items: List[SourceItem], sources_file: Path = DEFAULT_SOURCES_FILE) -> None:
    """Save the complete list of source items back to JSONL."""
    ensure_storage_dir(sources_file)
    temp_file = sources_file.with_suffix(".tmp")
    with open(temp_file, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(asdict(item), ensure_ascii=False) + "\n")
    temp_file.replace(sources_file)


def add_source(
    title: str,
    content: str,
    source_type: str,
    filename: Optional[str] = None,
    url: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    sources_file: Path = DEFAULT_SOURCES_FILE,
) -> SourceItem:
    """Add a new source item and persist to JSONL."""
    cleaned_content = content.strip()
    char_count = len(cleaned_content)
    est_tokens = char_count // 4

    item = SourceItem(
        id=str(uuid.uuid4()),
        title=title.strip() or (filename if filename else "Untitled Source"),
        source_type=source_type,
        content=cleaned_content,
        char_count=char_count,
        est_tokens=est_tokens,
        created_at=datetime.now(timezone.utc).isoformat(),
        filename=filename,
        url=url,
        metadata=metadata or {},
    )

    items = load_sources(sources_file)
    items.insert(0, item)  # Latest first
    save_sources(items, sources_file)
    return item


def delete_source(source_id: str, sources_file: Path = DEFAULT_SOURCES_FILE) -> bool:
    """Remove a source item by ID."""
    items = load_sources(sources_file)
    initial_len = len(items)
    filtered = [item for item in items if item.id != source_id]
    if len(filtered) < initial_len:
        save_sources(filtered, sources_file)
        return True
    return False


def clear_sources(sources_file: Path = DEFAULT_SOURCES_FILE) -> None:
    """Clear all sources from JSONL."""
    save_sources([], sources_file)


# ---------------------------------------------------------------------------
# Content Extraction Helpers
# ---------------------------------------------------------------------------

def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract plain text from PDF bytes using pymupdf with pypdf fallback."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        extracted_pages: List[str] = []
        for idx, page in enumerate(doc):
            text = page.get_text() or ""
            if text.strip():
                extracted_pages.append(f"--- Page {idx + 1} ---\n{text.strip()}")
        doc.close()
        if extracted_pages:
            return "\n\n".join(extracted_pages)
    except Exception:
        pass

    reader = PdfReader(io.BytesIO(file_bytes))
    extracted_pages: List[str] = []
    for idx, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip():
            extracted_pages.append(f"--- Page {idx + 1} ---\n{text.strip()}")
    return "\n\n".join(extracted_pages)


def extract_text_from_txt(file_bytes: bytes) -> str:
    """Decode raw txt/md bytes into unicode string."""
    try:
        return file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return file_bytes.decode("latin-1", errors="replace")


def fetch_url_text(url: str, timeout: int = 12) -> Tuple[str, str]:
    """Fetch URL and extract readable title and body text."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
    }
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # Remove script, style, and navigation tags
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    title = (soup.title.string.strip() if soup.title and soup.title.string else url)

    # Extract body paragraphs and text
    text = soup.get_text(separator="\n", strip=True)
    return title, text


# ---------------------------------------------------------------------------
# Context Packing for Agnes 512K Window
# ---------------------------------------------------------------------------

@dataclass
class PackedContextResult:
    budget_chars: int
    budget_tokens: int
    packed_chars: int
    packed_tokens: int
    packed_sources: List[SourceItem]
    excluded_sources: List[SourceItem]
    utilization_pct: float
    full_text: str


def pack_sources_for_context(
    sources: List[SourceItem],
    char_budget: int,
) -> PackedContextResult:
    """Pack sources greedily into the specified character budget.

    Calculates tokens as approx chars // 4.
    """
    packed: List[SourceItem] = []
    excluded: List[SourceItem] = []
    current_chars = 0
    compiled_texts: List[str] = []

    for item in sources:
        # Header formatting per source
        header = f"\n=== SOURCE: {item.title} (Type: {item.source_type}) ===\n"
        source_block = f"{header}{item.content}\n"
        source_len = len(source_block)

        if current_chars + source_len <= char_budget:
            packed.append(item)
            compiled_texts.append(source_block)
            current_chars += source_len
        else:
            excluded.append(item)

    packed_tokens = current_chars // 4
    budget_tokens = char_budget // 4
    utilization = (current_chars / char_budget * 100.0) if char_budget > 0 else 0.0

    return PackedContextResult(
        budget_chars=char_budget,
        budget_tokens=budget_tokens,
        packed_chars=current_chars,
        packed_tokens=packed_tokens,
        packed_sources=packed,
        excluded_sources=excluded,
        utilization_pct=round(utilization, 2),
        full_text="".join(compiled_texts),
    )
