"""Isolated web search module using DuckDuckGo Search (ddgs).

Default is OFF in the Streamlit application.
Returns clean structured search results without crashing on network or rate limit issues.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def search_web(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Execute search query using ddgs and return list of results.

    Returns:
        List[Dict[str, Any]]: List of dicts with 'title', 'href', 'body'.
    """
    if not query or not query.strip():
        return []

    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            raw_results = list(ddgs.text(query.strip(), max_results=max_results))

        results: List[Dict[str, Any]] = []
        for r in raw_results:
            results.append(
                {
                    "title": r.get("title", "Untitled"),
                    "href": r.get("href", r.get("link", "")),
                    "body": r.get("body", r.get("snippet", "")),
                }
            )
        return results
    except Exception as exc:
        logger.warning("Web search failed: %s", exc)
        return []
