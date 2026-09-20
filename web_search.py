"""Compatibility wrapper for optional DDGS web search.

New code should use ``src.web_search.search_web`` to receive both hits and an
error message. This wrapper preserves the legacy list-only interface.
"""

from __future__ import annotations

from typing import Any, Dict, List

from src.web_search import search_web as _search_web


def search_web(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Return normalized web hits through the legacy list-only interface.

    Args:
        query: Search query text.
        max_results: Requested maximum; the active implementation caps it at 3.

    Returns:
        Hit dictionaries with ``title``, ``href``, ``text``, ``origin``, and
        legacy ``body`` keys. Returns an empty list when search fails.
    """
    hits, _error = _search_web(query, max_results=max_results)
    return [hit | {"body": hit["text"]} for hit in hits]
