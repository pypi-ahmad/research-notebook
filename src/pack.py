"""Chunk ranking with embedded Qdrant and context window packing.

Hard rules:
- Free embedded Qdrant, qdrant-client, path="data/qdrant". No Qdrant Cloud.
- Rank chunks by vector similarity to user query, then pack into char context cap.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchAny,
    MatchValue,
    PointStruct,
    VectorParams,
)

from src.config import QDRANT_COLLECTION, QDRANT_PATH

DEFAULT_QDRANT_PATH = QDRANT_PATH
COLLECTION_NAME = QDRANT_COLLECTION
VECTOR_DIM = 384
QDRANT_LOCK_MESSAGE = (
    "Qdrant is locked. Close other apps using data/qdrant, then retry."
)


def embed_text(text: str) -> list[float]:
    """Create a deterministic local hashing vector without model downloads.

    Args:
        text: Text to embed.

    Returns:
        Unit-normalized vector of ``VECTOR_DIM`` values, or an all-zero vector
        when the input has no token matches.
    """
    vector = [0.0] * VECTOR_DIM
    tokens = re.findall(r"[\w.-]+", text.casefold())
    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "little") % VECTOR_DIM
        vector[bucket] += 1.0 if digest[4] & 1 else -1.0
    magnitude = math.sqrt(sum(value * value for value in vector))
    return [value / magnitude for value in vector] if magnitude else vector


def chunk_text(
    text: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 150,
) -> List[str]:
    """Split text into overlapping, approximately sentence-aligned chunks.

    Args:
        text: Source text to divide.
        chunk_size: Target maximum characters per chunk.
        chunk_overlap: Characters retained from the previous chunk.

    Returns:
        Non-empty chunks in source order.
    """
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
        boundary_start = min(start + 800, end)
        split_point = cleaned.rfind("\n\n", boundary_start, end)
        if split_point == -1 or split_point <= start:
            split_point = cleaned.rfind(". ", boundary_start, end)
        if split_point == -1 or split_point <= start:
            split_point = cleaned.rfind("\n", boundary_start, end)
        if split_point == -1 or split_point <= start:
            split_point = cleaned.rfind(" ", boundary_start, end)
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
    """Open an embedded Qdrant client at the requested local path.

    Args:
        path: Local embedded Qdrant storage directory.

    Returns:
        Open Qdrant client; callers must close it.
    """
    os.makedirs(path, exist_ok=True)
    return QdrantClient(path=path)


def _raise_qdrant_error(error: Exception) -> None:
    message = str(error).casefold()
    if "lock" in message or "already accessed by another instance" in message:
        raise RuntimeError(QDRANT_LOCK_MESSAGE) from error
    raise error


def init_collection(
    client: QdrantClient, collection_name: str = COLLECTION_NAME
) -> None:
    """Create the configured vector collection when it does not exist.

    Args:
        client: Open embedded Qdrant client.
        collection_name: Collection to create or retain.
    """
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
    """Chunk source objects and upsert them into embedded Qdrant.

    Args:
        sources: Objects exposing ``id``, ``title``, ``content``, and origin
            metadata used in payloads.
        qdrant_path: Local embedded Qdrant storage directory.
        collection_name: Target collection name.

    Returns:
        Number of points submitted for upsert.

    Raises:
        RuntimeError: If embedded Qdrant is locked by another process.
    """
    try:
        client = get_qdrant_client(qdrant_path)
    except Exception as error:
        _raise_qdrant_error(error)
    try:
        init_collection(client, collection_name)

        points: List[PointStruct] = []
        all_chunk_texts: List[str] = []
        metadata_list: List[Dict[str, Any]] = []

        for src in sources:
            source_id = getattr(src, "id", str(uuid.uuid4()))
            title = getattr(src, "title", "Untitled")
            source_type = getattr(src, "source_type", "unknown")
            origin = getattr(src, "origin", source_type)
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
                        "origin": origin,
                        "chunk_index": idx,
                        "char_count": len(chk),
                        "est_tokens": len(chk) // 4,
                    }
                )

        if not all_chunk_texts:
            return 0

        vectors = [embed_text(text) for text in all_chunk_texts]

        for idx, (vec, meta) in enumerate(zip(vectors, metadata_list)):
            points.append(
                PointStruct(
                    id=str(uuid.uuid5(uuid.NAMESPACE_URL, meta["chunk_id"])),
                    vector=vec,
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


def get_source_point_counts(
    source_ids: List[str],
    qdrant_path: str = DEFAULT_QDRANT_PATH,
    collection_name: str = COLLECTION_NAME,
) -> Dict[str, int]:
    """Count stored Qdrant chunks for each requested source ID.

    Args:
        source_ids: Source UUIDs to count.
        qdrant_path: Local embedded Qdrant storage directory.
        collection_name: Target collection name.

    Returns:
        Mapping of every supplied source ID to its point count.

    Raises:
        RuntimeError: If embedded Qdrant is locked by another process.
    """
    counts = {source_id: 0 for source_id in source_ids}
    if not source_ids:
        return counts
    try:
        client = get_qdrant_client(qdrant_path)
    except Exception as error:
        _raise_qdrant_error(error)
    try:
        if not client.collection_exists(collection_name):
            return counts
        for source_id in source_ids:
            source_filter = Filter(
                must=[
                    FieldCondition(
                        key="source_id", match=MatchValue(value=source_id)
                    )
                ]
            )
            counts[source_id] = client.count(
                collection_name=collection_name,
                count_filter=source_filter,
                exact=True,
            ).count
        return counts
    except Exception as error:
        _raise_qdrant_error(error)
    finally:
        client.close()


def delete_source_points(
    source_id: str,
    qdrant_path: str = DEFAULT_QDRANT_PATH,
    collection_name: str = COLLECTION_NAME,
) -> int:
    """Delete all Qdrant points associated with one source ID.

    Args:
        source_id: Source UUID whose chunks are removed.
        qdrant_path: Local embedded Qdrant storage directory.
        collection_name: Target collection name.

    Returns:
        Number of deleted points.

    Raises:
        RuntimeError: If embedded Qdrant is locked by another process.
    """
    try:
        client = get_qdrant_client(qdrant_path)
    except Exception as error:
        _raise_qdrant_error(error)
    try:
        if not client.collection_exists(collection_name):
            return 0
        source_filter = Filter(
            must=[
                FieldCondition(key="source_id", match=MatchValue(value=source_id))
            ]
        )
        point_count = client.count(
            collection_name=collection_name,
            count_filter=source_filter,
            exact=True,
        ).count
        client.delete(
            collection_name=collection_name,
            points_selector=FilterSelector(filter=source_filter),
            wait=True,
        )
        return point_count
    except Exception as error:
        _raise_qdrant_error(error)
    finally:
        client.close()


@dataclass
class PackedChunk:
    """One retrieved uploaded chunk selected for packed context.

    Attributes:
        source_id: UUID of the stored source.
        chunk_id: Stable source-local chunk identifier.
        title: Source title captured in the Qdrant payload.
        source_type: Source origin/type captured in the payload.
        text: Retrieved chunk text.
        score: Qdrant similarity score.
        char_count: Number of characters in ``text``.
        est_tokens: Character-based token estimate.
    """
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
    """Packed retrieval context and provenance for a query.

    Attributes:
        packed_chunks: Uploaded chunks included under the budget.
        packed_chars: Characters included in all packed sections.
        packed_tokens: Character-based token estimate.
        char_cap: Requested character ceiling.
        total_candidates: Qdrant candidates considered before packing.
        full_text: Prompt-ready uploaded chunks followed by optional web snippets.
        citations: ``source_id`` and ``chunk_id`` provenance for packed chunks.
    """
    packed_chunks: List[PackedChunk]
    packed_chars: int
    packed_tokens: int
    char_cap: int
    total_candidates: int
    full_text: str
    citations: List[Dict[str, str]]


def rank_and_pack_chunks(
    query: str,
    sources: Optional[List[Any]] = None,
    char_cap: int = 200_000,
    qdrant_path: str = DEFAULT_QDRANT_PATH,
    collection_name: str = COLLECTION_NAME,
    top_k: int = 50,
    web_snippets: Optional[List[Dict[str, Any]]] = None,
) -> PackedChunksResult:
    """Retrieve top Qdrant chunks, pack them, then append optional web snippets.

    Args:
        query: Query used for vector retrieval; empty queries scroll points.
        sources: Optional sources used to constrain retrieval and refresh indexing.
        char_cap: Maximum characters in the final packed context.
        qdrant_path: Local embedded Qdrant storage directory.
        collection_name: Target collection name.
        top_k: Maximum Qdrant candidates to retrieve.
        web_snippets: Optional normalized web hits appended after source chunks.

    Returns:
        Prompt-ready context, packed uploaded chunks, and source/chunk citations.

    Raises:
        RuntimeError: If embedded Qdrant is locked by another process.
    """
    if sources is not None and not sources:
        if not web_snippets:
            return PackedChunksResult([], 0, 0, char_cap, 0, "", [])

    # Ensure sources are indexed if provided
    if sources is not None and len(sources) > 0:
        index_sources_to_qdrant(
            sources, qdrant_path=qdrant_path, collection_name=collection_name
        )

    client = get_qdrant_client(qdrant_path)
    try:
        init_collection(client, collection_name)
        if query.strip():
            query_vector = embed_text(query.strip())
            allowed_sources = [getattr(source, "id", "") for source in (sources or [])]
            query_filter = None
            if allowed_sources:
                query_filter = Filter(
                    must=[
                        FieldCondition(
                            key="source_id",
                            match=MatchAny(any=allowed_sources),
                        )
                    ]
                )
            search_response = client.query_points(
                collection_name=collection_name,
                query=query_vector,
                query_filter=query_filter,
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
                    chunk_id=payload.get(
                        "chunk_id", f"{payload.get('source_id', 'unknown')}_0"
                    ),
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

        web_separator = (
            "\n=== WEB SNIPPETS (origin=web; not uploaded sources) ===\n"
        )
        web_started = False
        for snippet in (web_snippets or [])[:3]:
            web_block = (
                f"web: {snippet.get('title', 'Untitled')}\n"
                f"URL: {snippet.get('href', '')}\n"
                f"{snippet.get('text', '')}\n"
            )
            addition = (web_separator if not web_started else "") + web_block
            if current_chars + len(addition) <= char_cap:
                compiled_sections.append(addition)
                current_chars += len(addition)
                web_started = True

        return PackedChunksResult(
            packed_chunks=packed,
            packed_chars=current_chars,
            packed_tokens=current_chars // 4,
            char_cap=char_cap,
            total_candidates=len(ranked_items),
            full_text="".join(compiled_sections),
            citations=[
                {"source_id": item.source_id, "chunk_id": item.chunk_id}
                for item in packed
            ],
        )
    finally:
        client.close()
