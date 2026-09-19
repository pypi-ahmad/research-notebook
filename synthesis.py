"""Synthesis and Question Answering Engine.

Implements:
- Ask: Answers queries with verbatim quotes and explicit source_id citations.
- Brief: Generates structured research briefs {claim, evidence[], gaps, followups[]} saved to data/briefs/.
- Web Augmentation: Appends 3 snippets labeled 'web:' and never treats them as uploaded sources.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import RateLimitError

from client import build_client
from src.pack import PackedChunksResult, rank_and_pack_chunks
from web_search import search_web

DEFAULT_BRIEFS_DIR = Path("data/briefs")
DEFAULT_CACHE_DIR = Path("data/cache")


def call_chat_completion_with_retry(client: Any, max_retries: int = 5, **kwargs: Any) -> Any:
    """Execute chat completion with backoff on API rate limit errors."""
    delay = 8.0
    for attempt in range(max_retries):
        try:
            return client.chat.completions.create(**kwargs)
        except RateLimitError:
            if attempt < max_retries - 1:
                time.sleep(delay)
                delay = min(delay * 1.5, 30.0)
            else:
                raise


def format_web_snippets(snippets: List[Dict[str, Any]]) -> str:
    """Format web search snippets strictly labeled as web results."""
    if not snippets:
        return ""

    lines = [
        "\n=== WEB SEARCH RESULTS (AUXILIARY WEB DATA - NOT UPLOADED SOURCES) ===",
        "NOTE: Never treat web results as uploaded sources. Label citations for these as web:.\n",
    ]
    for idx, s in enumerate(snippets[:3], start=1):
        lines.append(f"web: [{s.get('title', 'Web Result')}] (URL: {s.get('href', '')})")
        lines.append(f"Snippet: {s.get('body', '')}\n")
    return "\n".join(lines)


def ask_question(
    query: str,
    sources: Optional[List[Any]] = None,
    char_cap: int = 200_000,
    web_enabled: bool = False,
    provider_id: str = "agnes",
    model_override: Optional[str] = None,
    temperature: float = 0.2,
) -> Dict[str, Any]:
    """Answer user query using ranked Qdrant chunks and optional web snippets."""
    if not query.strip():
        raise ValueError("Query cannot be empty.")

    # 1. Rank chunks via embedded Qdrant and pack into character context cap
    packed: PackedChunksResult = rank_and_pack_chunks(
        query=query,
        sources=sources,
        char_cap=char_cap,
    )

    # 2. Gather web snippets if enabled (strictly up to 3 snippets)
    web_snippets: List[Dict[str, Any]] = []
    web_text = ""
    if web_enabled:
        web_snippets = search_web(query, max_results=3)
        web_text = format_web_snippets(web_snippets)

    # 3. Construct system and user prompt
    system_prompt = (
        "You are an evidence-grounded research assistant.\n"
        "Rules:\n"
        "1. Ground all statements strictly in the provided sources.\n"
        "2. For every key fact or claim, provide verbatim quotes and the corresponding source_id in format: "
        "[<source_id>: \"exact quote\"].\n"
        "3. If auxiliary web snippets are provided, they are NOT uploaded sources. Any information from them "
        "must be explicitly prefixed with [web: \"quote or summary\"].\n"
        "4. If the provided sources do not contain sufficient evidence to answer, state clearly what cannot be established."
    )

    user_content = (
        f"USER RESEARCH QUESTION:\n{query}\n\n"
        f"AVAILABLE SOURCE CONTEXT (Ranked by relevance):\n"
        f"{packed.full_text if packed.full_text else 'No uploaded source chunks available.'}\n"
        f"{web_text}"
    )

    client, default_model = build_client(provider_id)
    target_model = model_override or default_model

    response = call_chat_completion_with_retry(
        client,
        model=target_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        temperature=temperature,
    )

    answer_text = response.choices[0].message.content or ""

    # Extract citation list: [{source, quote}, ...]
    citations: List[Dict[str, str]] = []
    patterns = [
        r'\[(?P<source>[^\]:]+):\s*"(?P<quote>[^"]+)"\]',
        r'\[(?P<source>[^\]]+)\]:\s*"(?P<quote>[^"]+)"',
        r'\[(?P<source>[^\]]+)\]\s*"(?P<quote>[^"]+)"',
    ]
    seen_citations = set()
    for pat in patterns:
        for match in re.finditer(pat, answer_text):
            src = match.group("source").strip()
            quote = match.group("quote").strip()
            key = (src, quote)
            if key not in seen_citations:
                seen_citations.add(key)
                citations.append({"source": src, "quote": quote})

    # Save to data/cache/last_ask.json
    DEFAULT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    last_ask_file = DEFAULT_CACHE_DIR / "last_ask.json"
    ask_record = {
        "query": query,
        "answer": answer_text,
        "citations": citations,
        "packed_chars": packed.packed_chars,
        "packed_tokens": packed.packed_tokens,
        "packed_chunks": [
            {
                "source_id": c.source_id,
                "chunk_id": c.chunk_id,
                "title": c.title,
                "score": c.score,
            }
            for c in packed.packed_chunks
        ],
        "web_snippets": web_snippets,
        "model_used": target_model,
        "provider_id": provider_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with open(last_ask_file, "w", encoding="utf-8") as f:
        json.dump(ask_record, f, indent=2, ensure_ascii=False)

    return {
        "answer": answer_text,
        "citations": citations,
        "packed_chunks": packed.packed_chunks,
        "packed_chars": packed.packed_chars,
        "packed_tokens": packed.packed_tokens,
        "web_snippets": web_snippets,
        "model_used": target_model,
        "provider_id": provider_id,
    }


def generate_brief(
    topic: str,
    sources: Optional[List[Any]] = None,
    char_cap: int = 200_000,
    web_enabled: bool = False,
    provider_id: str = "agnes",
    model_override: Optional[str] = None,
    output_dir: Path = DEFAULT_BRIEFS_DIR,
) -> Dict[str, Any]:
    """Generate structured research brief with {claim, evidence[], gaps, followups[]}."""
    if not topic.strip():
        raise ValueError("Topic cannot be empty.")

    # 1. Rank chunks relevant to topic
    packed: PackedChunksResult = rank_and_pack_chunks(
        query=topic,
        sources=sources,
        char_cap=char_cap,
    )

    web_snippets: List[Dict[str, Any]] = []
    web_text = ""
    if web_enabled:
        web_snippets = search_web(topic, max_results=3)
        web_text = format_web_snippets(web_snippets)

    system_prompt = (
        "You are an expert research synthesizer.\n"
        "Create a rigorous, structured research brief in GitHub-flavored Markdown.\n"
        "You MUST organize the brief using these exact sections:\n"
        "# Research Brief: <Topic>\n\n"
        "## Executive Summary\n"
        "<A 2-3 paragraph synthesis of current state>\n\n"
        "## Claims and Evidence\n"
        "List each key finding with its supporting verbatim evidence:\n"
        "- **Claim**: <Clear assertion>\n"
        "  - Evidence:\n"
        "    - [<source_id>]: \"<verbatim quote supporting the assertion>\"\n\n"
        "## Gaps\n"
        "List unresolved questions, omissions, or ambiguities in the evidence:\n"
        "- **Gap**: <Identified gap and why it matters>\n\n"
        "## Follow-ups\n"
        "List concrete next steps or research avenues to investigate:\n"
        "- **Follow-up**: <Actionable inquiry or experiment>\n\n"
        "Rules:\n"
        "- Ground strictly in provided source chunks.\n"
        "- Every evidence entry MUST cite [<source_id>] and verbatim quote in quotation marks.\n"
        "- If web snippets exist, cite them as [web: ...] and never treat them as uploaded sources."
    )

    user_content = (
        f"TOPIC / RESEARCH OBJECTIVE:\n{topic}\n\n"
        f"PACKED SOURCE EVIDENCE:\n"
        f"{packed.full_text if packed.full_text else 'No uploaded source chunks available.'}\n"
        f"{web_text}"
    )

    client, default_model = build_client(provider_id)
    target_model = model_override or default_model

    response = call_chat_completion_with_retry(
        client,
        model=target_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        temperature=0.2,
    )

    brief_markdown = response.choices[0].message.content or ""

    # Persist brief to data/briefs/
    output_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^\w\-]", "_", topic.lower().strip())[:40]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"brief_{timestamp}_{slug}.md"
    file_path = output_dir / filename

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(brief_markdown)

    # Also save to data/cache/last_brief.md
    DEFAULT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    last_brief_file = DEFAULT_CACHE_DIR / "last_brief.md"
    last_brief_file.write_text(brief_markdown, encoding="utf-8")

    return {
        "file_path": str(file_path),
        "filename": filename,
        "content": brief_markdown,
        "packed_chars": packed.packed_chars,
        "packed_tokens": packed.packed_tokens,
        "web_snippets": web_snippets,
        "model_used": target_model,
        "provider_id": provider_id,
    }
