# Citation and quote grounding

This document explains how quote spans are structured, extracted, and verified in Research Notebook.

## Citation format

Every factual claim in model answers and research briefs must cite supporting evidence using this syntax:

```
[source_id: "verbatim quote from source text"]
```

When web search is enabled, external web findings use the prefix `web:` instead of a source ID:

```
[web: "snippet text or title"]
```

This format provides a clear audit trail. Anyone reviewing an answer can trace a quote back to the exact file or note in `data/sources/sources.jsonl`.

## Chunk preparation and Qdrant payload

When text is added to the system, `sources_manager.py` assigns a unique UUID (`source_id`).

`src/pack.py` breaks each document into chunks of 700 characters with 100 characters of overlap. Each chunk carries metadata into the embedded Qdrant index under the payload format `{source_id, chunk_id, text}`:

```python
{
    "source_id": "6f21e5df-08d1-4191-88fc-d2e8e788bc53",
    "chunk_id": "6f21e5df-08d1-4191-88fc-d2e8e788bc53_0",
    "text": "The Chronos engine employs dedicated sink tokens...",
    "title": "Chronos Engine: KV Cache Retention",
    "source_type": "upload",
    "chunk_index": 0,
    "char_count": 684,
    "est_tokens": 171
}
```

When Qdrant ranks chunks by query similarity, each selected chunk is formatted into the prompt context with its header:

```
=== SOURCE CHUNK [source_id: 6f21e5df-08d1-4191-88fc-d2e8e788bc53] (Title: Chronos Engine..., Score: 0.884) ===
The Chronos engine employs dedicated sink tokens and selective eviction to maintain KV-cache coherence over extended generation horizons...
```

## Prompt instruction

The system prompt in `synthesis.py` instructs the model to follow two strict grounding rules:

1. Base claims only on facts present in the supplied chunks.
2. Pair every factual assertion with a direct quote wrapped in quotation marks and attribute it to the chunk's `source_id`.

Example prompt instruction:

```
For every key fact or claim, provide verbatim quotes and the corresponding source_id in format: [<source_id>: "exact quote"].
```

## Citations list extraction

In addition to embedded in-line citations, `synthesis.py` parses all citation spans into a structured list:

```python
[
    {
        "source": "6f21e5df-08d1-4191-88fc-d2e8e788bc53",
        "quote": "In rigorous long-context trials, Chronos achieved 99.1% needle recall while using exactly 16 sink tokens per attention layer"
    }
]
```

This list is displayed in the Ask tab under **Grounded Citations List** and persisted to `data/cache/last_ask.json`.

## How quote spans are verified

A citation can be programmatically verified against the raw text:

1. Locate the record in `data/sources/sources.jsonl` matching `source_id`.
2. Extract the quote substring enclosed within the quotation marks.
3. Check whether the normalized substring exists inside the stored document content.

If the quote matches the source text exactly, the assertion is confirmed. If the substring is absent, the citation indicates a paraphrase or hallucination rather than a verbatim quote.

## Web snippet isolation

Web search snippets from DuckDuckGo are appended after all document chunks. They are marked with an explicit header:

```
=== WEB SEARCH RESULTS (AUXILIARY WEB DATA - NOT UPLOADED SOURCES) ===
web: [Title] (URL: https://...)
Snippet: ...
```

The model prompt forbids assigning a document `source_id` to web search text. Web claims must use the `[web: ...]` label. This rule prevents unvetted search results from masquerading as canonical uploaded research documents.
