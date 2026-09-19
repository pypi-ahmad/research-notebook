"""Chunk ranking with embedded Qdrant and context window packing.

Hard rules:
- Free embedded Qdrant, qdrant-client, path="data/qdrant". No Qdrant Cloud.
- Rank chunks by vector similarity to user query, then pack into char context cap.
"""

from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastembed import TextEmbedding
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

DEFAULT_QDRANT_PATH = "data/qdrant"
COLLECTION_NAME = "source_chunks"
VECTOR_DIM = 384
EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"

# Lazy-loaded embedding model singleton
_EMBEDDER: Optional[TextEmbedding] = None


def get_embedder() -> TextEmbedding:
    global _EMBEDDER
    if _EMBEDDER is None:
        _EMBEDDER = TextEmbedding(model_name=EMBEDDING_MODEL_NAME)
    return _EMBEDDER


def chunk_text(
    text: str,
    chunk_size: int = 700,
    chunk_overlap: int = 100,
) -> List[str]:
    """Split text into overlapping character chunks cleanly by sentences/paragraphs."""
    cleaned = text.strip()
    if not cleaned:
        return []
    if len(cleaned) <= chunk_size:
        return [cleaned]

    chunks: List[str] = []
    start = 0
    while start < len(cleaned):
        end = start + chunk_size
        if end >= len(cleaned):
            chunk = cleaned[start:].strip()
            if chunk:
                chunks.append(chunk)
            break

        # Look for sentence or paragraph boundary near end
        split_point = cleaned.rfind("\n\n", start, end)
        if split_point == -1 or split_point <= start:
            split_point = cleaned.rfind(". ", start, end)
        if split_point == -1 or split_point <= start:
            split_point = cleaned.rfind("\n", start, end)
        if split_point == -1 or split_point <= start:
            split_point = cleaned.rfind(" ", start, end)
        if split_point == -1 or split_point <= start:
            split_point = end
        else:
            split_point += 1

        chunk = cleaned[start:split_point].strip()
        if chunk:
            chunks.append(chunk)

        start = max(split_point - chunk_overlap, start + 1)
        if start >= len(cleaned):
            break

    return chunks


def get_qdrant_client(path: str = DEFAULT_QDRANT_PATH) -> QdrantClient:
    """Instantiate embedded Qdrant client."""
    os.makedirs(path, exist_ok=True)
    return QdrantClient(path=path)


def init_collection(client: QdrantClient, collection_name: str = COLLECTION_NAME) -> None:
    """Ensure collection exists in embedded Qdrant."""
    collections = [c.name for c in client.get_collections().collections]
    if collection_name not in collections:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
        )


def index_sources_to_qdrant(
    sources: List[Any],
    qdrant_path: str = DEFAULT_QDRANT_PATH,
    collection_name: str = COLLECTION_NAME,
) -> int:
    """Chunk and index source items into embedded Qdrant vector store."""
    client = get_qdrant_client(qdrant_path)
    try:
        init_collection(client, collection_name)

        points: List[PointStruct] = []
        all_chunk_texts: List[str] = []
        metadata_list: List[Dict[str, Any]] = []

        point_num = 1
        for src in sources:
            source_id = getattr(src, "id", str(uuid.uuid4()))
            title = getattr(src, "title", "Untitled")
            source_type = getattr(src, "source_type", "unknown")
            content = getattr(src, "content", "")

            chunks = chunk_text(content)
            for idx, chk in enumerate(chunks):
                all_chunk_texts.append(chk)
                chunk_id = f"{source_id}_{idx}"
                metadata_list.append(
                    {
                        "source_id": source_id,
                        "chunk_id": chunk_id,
                        "text": chk,
                        "title": title,
                        "source_type": source_type,
                        "chunk_index": idx,
                        "char_count": len(chk),
                        "est_tokens": len(chk) // 4,
                    }
                )

        if not all_chunk_texts:
            return 0

        embedder = get_embedder()
        vectors = list(embedder.embed(all_chunk_texts))

        for idx, (vec, meta) in enumerate(zip(vectors, metadata_list)):
            points.append(
                PointStruct(
                    id=idx + 1,
                    vector=vec.tolist(),
                    payload=meta,
                )
            )

        # Upsert in batches of 100
        batch_size = 100
        for i in range(0, len(points), batch_size):
            client.upsert(
                collection_name=collection_name,
                points=points[i : i + batch_size],
            )

        return len(points)
    finally:
        client.close()


@dataclass
class PackedChunk:
    source_id: str
    chunk_id: str
    title: str
    source_type: str
    text: str
    score: float
    char_count: int
    est_tokens: int


@dataclass
class PackedChunksResult:
    packed_chunks: List[PackedChunk]
    packed_chars: int
    packed_tokens: int
    char_cap: int
    total_candidates: int
    full_text: str


def rank_and_pack_chunks(
    query: str,
    sources: Optional[List[Any]] = None,
    char_cap: int = 200_000,
    qdrant_path: str = DEFAULT_QDRANT_PATH,
    collection_name: str = COLLECTION_NAME,
    top_k: int = 50,
) -> PackedChunksResult:
    """Rank source chunks by similarity to query using Qdrant, then pack into char_cap."""
    # Ensure sources are indexed if provided
    if sources is not None and len(sources) > 0:
        index_sources_to_qdrant(sources, qdrant_path=qdrant_path, collection_name=collection_name)

    client = get_qdrant_client(qdrant_path)
    try:
        init_collection(client, collection_name)
        embedder = get_embedder()

        if query.strip():
            query_vector = list(embedder.embed([query.strip()]))[0].tolist()
            search_response = client.query_points(
                collection_name=collection_name,
                query=query_vector,
                limit=top_k,
            )
            raw_points = search_response.points
        else:
            # If no query, scroll points in order
            scroll_response, _ = client.scroll(
                collection_name=collection_name,
                limit=top_k,
                with_payload=True,
                with_vectors=False,
            )
            raw_points = scroll_response

        ranked_items: List[PackedChunk] = []
        for p in raw_points:
            payload = p.payload or {}
            score = getattr(p, "score", 1.0)
            text = payload.get("text", "")
            char_count = len(text)
            ranked_items.append(
                PackedChunk(
                    source_id=payload.get("source_id", "unknown"),
                    chunk_id=payload.get("chunk_id", f"{payload.get('source_id', 'unknown')}_0"),
                    title=payload.get("title", "Untitled"),
                    source_type=payload.get("source_type", "unknown"),
                    text=text,
                    score=float(score) if score is not None else 1.0,
                    char_count=char_count,
                    est_tokens=char_count // 4,
                )
            )

        # Pack into character context cap
        packed: List[PackedChunk] = []
        current_chars = 0
        compiled_sections: List[str] = []

        for item in ranked_items:
            chunk_header = (
                f"\n=== SOURCE CHUNK [source_id: {item.source_id}] "
                f"(Title: {item.title}, Type: {item.source_type}, Score: {item.score:.3f}) ===\n"
            )
            formatted_block = f"{chunk_header}{item.text}\n"
            block_len = len(formatted_block)

            if current_chars + block_len <= char_cap:
                packed.append(item)
                compiled_sections.append(formatted_block)
                current_chars += block_len

        return PackedChunksResult(
            packed_chunks=packed,
            packed_chars=current_chars,
            packed_tokens=current_chars // 4,
            char_cap=char_cap,
            total_candidates=len(ranked_items),
            full_text="".join(compiled_sections),
        )
    finally:
        client.close()
