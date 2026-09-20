"""Smoke optional DDGS search and web-last context packing without Agnes."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.ingest import load_sources
from src.pack import rank_and_pack_chunks
from src.web_search import search_web

QUESTION = "What is the current year according to the search snippets?"
CACHE_PATH = ROOT / "data" / "cache" / "last_web.json"


def main() -> int:
    """Verify optional web-hit normalization and web-last context packing.

    Returns:
        Zero after writing either DDGS hits or a failure description to cache.
    """
    hits, error = search_web(QUESTION, max_results=3)
    if len(hits) > 3:
        raise AssertionError("Web search returned more than three hits.")
    if any(hit.get("origin") != "web" for hit in hits):
        raise AssertionError("Every hit must have origin=web.")

    packed = rank_and_pack_chunks(
        QUESTION,
        sources=load_sources(),
        char_cap=200_000,
        top_k=12,
        web_snippets=hits,
    )
    if hits:
        web_position = packed.full_text.find("=== WEB SNIPPETS")
        source_position = packed.full_text.find("=== SOURCE CHUNK")
        if web_position < 0 or (source_position >= 0 and web_position < source_position):
            raise AssertionError("Web snippets were not packed after uploaded chunks.")

    record = {
        "query": QUESTION,
        "hits": hits,
        "error": error,
    }
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
