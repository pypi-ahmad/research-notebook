"""Agnes AI client initialization and provider routing.

Follows project rules:
- Chat completions via official openai SDK.
- Default provider: Agnes AI with model agnes-3.0-flash and base URL https://apihub.agnes-ai.com/v1.
- AGNESAI_API_KEY sourced from user environment variables only (never logged or committed).
- Optional providers (OpenAI, Google) exposed only if required environment variables are set.
- No API calls triggered during client creation.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(override=False)

DEFAULT_AGNES_BASE_URL = "https://apihub.agnes-ai.com/v1"
DEFAULT_AGNES_MODEL = "agnes-3.0-flash"
GOOGLE_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


@dataclass
class ProviderInfo:
    id: str
    display_name: str
    base_url: str
    models: List[str]
    default_model: str


def get_agnes_client() -> Tuple[OpenAI, str]:
    """Return a configured OpenAI SDK client instance for Agnes AI and the default model name.
    
    Raises:
        ValueError: If AGNESAI_API_KEY is not set.
    """
    api_key = os.environ.get("AGNESAI_API_KEY")
    if not api_key:
        raise ValueError("AGNESAI_API_KEY is not set in environment.")
    base_url = os.environ.get("AGNESAI_BASE_URL", DEFAULT_AGNES_BASE_URL)
    client = OpenAI(api_key=api_key, base_url=base_url)
    return client, DEFAULT_AGNES_MODEL


def get_available_providers() -> Dict[str, ProviderInfo]:
    """Inspect environment and return active providers whose keys exist."""
    providers: Dict[str, ProviderInfo] = {}

    agnes_key = os.environ.get("AGNESAI_API_KEY")
    if agnes_key:
        providers["agnes"] = ProviderInfo(
            id="agnes",
            display_name="Agnes AI (Default)",
            base_url=os.environ.get("AGNESAI_BASE_URL", DEFAULT_AGNES_BASE_URL),
            models=["agnes-3.0-flash"],
            default_model="agnes-3.0-flash",
        )

    openai_key = os.environ.get("OPENAI_API_KEY")
    openai_base = os.environ.get("OPENAI_BASE_URL")
    if openai_key and openai_base:
        providers["openai"] = ProviderInfo(
            id="openai",
            display_name="OpenAI Custom",
            base_url=openai_base.rstrip("/"),
            models=["gpt-5.6-luna", "gpt-5.6-terra"],
            default_model="gpt-5.6-luna",
        )

    google_key = os.environ.get("GOOGLE_API_KEY")
    if google_key:
        providers["google"] = ProviderInfo(
            id="google",
            display_name="Google Gemini",
            base_url=GOOGLE_OPENAI_BASE_URL,
            models=["gemini-3.5-flash-l"],
            default_model="gemini-3.5-flash-l",
        )

    return providers


def build_client(provider_id: str = "agnes") -> Tuple[OpenAI, str]:
    """Construct an OpenAI client for the given provider without making any network calls."""
    if provider_id == "agnes":
        return get_agnes_client()

    providers = get_available_providers()
    if provider_id not in providers:
        raise ValueError(
            f"Provider '{provider_id}' is not configured or missing required environment variables."
        )

    info = providers[provider_id]
    if provider_id == "openai":
        api_key = os.environ.get("OPENAI_API_KEY")
    elif provider_id == "google":
        api_key = os.environ.get("GOOGLE_API_KEY")
    else:
        raise ValueError(f"Unsupported provider: {provider_id}")

    client = OpenAI(api_key=api_key, base_url=info.base_url)
    return client, info.default_model
