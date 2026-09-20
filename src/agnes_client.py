"""Agnes AI client initialization.

Follows project rules:
- Chat completions via official openai SDK.
- Default provider: Agnes AI with model agnes-3.0-flash and base URL https://apihub.agnes-ai.com/v1.
- AGNESAI_API_KEY sourced from user environment variables only (never logged or committed).
- No API calls triggered during client creation.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from openai import OpenAI, RateLimitError

from src.config import AGNES_BASE_URL, AGNES_MODEL

DEFAULT_AGNES_BASE_URL = AGNES_BASE_URL
DEFAULT_AGNES_MODEL = AGNES_MODEL


@dataclass
class ProviderInfo:
    """Configuration exposed for an available language-model provider.

    Attributes:
        id: Stable provider identifier accepted by ``build_client``.
        display_name: Human-readable name for UI display.
        base_url: OpenAI-compatible API base URL.
        models: Models selectable for the provider.
        default_model: Model used when callers do not override it.
    """
    id: str
    display_name: str
    base_url: str
    models: List[str]
    default_model: str


def get_agnes_client() -> Tuple[OpenAI, str]:
    """Return a configured Agnes SDK client and its default model name.

    Returns:
        OpenAI-compatible client configured for Agnes and ``agnes-3.0-flash``.

    Raises:
        ValueError: If AGNESAI_API_KEY is not set.
    """
    api_key = os.environ.get("AGNESAI_API_KEY")
    if not api_key:
        raise ValueError("AGNESAI_API_KEY is not set in environment.")
    client = OpenAI(api_key=api_key, base_url=DEFAULT_AGNES_BASE_URL, timeout=120.0)
    return client, DEFAULT_AGNES_MODEL


def get_available_providers() -> Dict[str, ProviderInfo]:
    """Return the Agnes provider only when its environment key is available.

    Returns:
        Mapping from provider ID to configuration. The mapping is empty when
        ``AGNESAI_API_KEY`` is absent.
    """
    if not os.environ.get("AGNESAI_API_KEY"):
        return {}
    return {
        "agnes": ProviderInfo(
            id="agnes",
            display_name="Agnes AI",
            base_url=DEFAULT_AGNES_BASE_URL,
            models=[DEFAULT_AGNES_MODEL],
            default_model=DEFAULT_AGNES_MODEL,
        )
    }


def build_client(provider_id: str = "agnes") -> Tuple[OpenAI, str]:
    """Construct an Agnes SDK client without making a network request.

    Args:
        provider_id: Supported provider identifier; only ``agnes`` is valid.

    Returns:
        Configured OpenAI-compatible client and its default model name.

    Raises:
        ValueError: If the provider is unsupported or the Agnes key is absent.
    """
    if provider_id != "agnes":
        raise ValueError(f"Unsupported provider: {provider_id}")
    return get_agnes_client()


def call_chat_completion_with_retry(
    client: OpenAI, max_retries: int = 5, **kwargs: Any
) -> Any:
    """Call Chat Completions with bounded retry for HTTP 429 responses.

    Args:
        client: Configured OpenAI-compatible client.
        max_retries: Maximum attempts, including the first request.
        **kwargs: Keyword arguments passed to ``chat.completions.create``.

    Returns:
        The SDK chat-completion response.

    Raises:
        RateLimitError: If the final attempt is rate limited.
    """
    delay = 8.0
    for attempt in range(max_retries):
        try:
            return client.chat.completions.create(**kwargs)
        except RateLimitError:
            if attempt == max_retries - 1:
                raise
            time.sleep(delay)
            delay = min(delay * 1.5, 30.0)

    raise RuntimeError("Chat completion retry loop ended unexpectedly.")
