"""Provider routing and client helpers for Research Notebook.

Re-exports from src.agnes_client for convenient root imports.
"""

from __future__ import annotations

from src.agnes_client import (
    DEFAULT_AGNES_BASE_URL,
    DEFAULT_AGNES_MODEL,
    GOOGLE_OPENAI_BASE_URL,
    ProviderInfo,
    get_agnes_client,
    get_available_providers,
    build_client,
)

__all__ = [
    "DEFAULT_AGNES_BASE_URL",
    "DEFAULT_AGNES_MODEL",
    "GOOGLE_OPENAI_BASE_URL",
    "ProviderInfo",
    "get_agnes_client",
    "get_available_providers",
    "build_client",
]
