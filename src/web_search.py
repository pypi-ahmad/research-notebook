"""Failure-safe DDGS web search for optional context augmentation."""

from __future__ import annotations

from typing import Any


def search_web(
    query: str, max_results: int = 3
) -> tuple[list[dict[str, Any]], str | None]:
    """Return up to three normalized DDGS hits and an optional error message.

    Args:
        query: Search query text.
        max_results: Requested maximum; values above three are capped.

    Returns:
        A pair of ``(hits, error)``. Each hit has ``title``, ``href``, ``text``,
        and ``origin="web"``. On library or network failure, hits is empty and
        error contains a user-safe explanation.
    """
    if not query.strip():
        return [], None
    try:
        from ddgs import DDGS

        with DDGS() as ddgs:
            raw_hits = list(
                ddgs.text(query.strip(), max_results=min(max_results, 3))
            )
        hits = [
            {
                "title": hit.get("title", "Untitled"),
                "href": hit.get("href", hit.get("link", "")),
                "text": hit.get("body", hit.get("snippet", "")),
                "origin": "web",
            }
            for hit in raw_hits[:3]
        ]
        return hits, None
    except Exception as error:
        return [], f"Web search unavailable: {error}"


__all__ = ["search_web"]
