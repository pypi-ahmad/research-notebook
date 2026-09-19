# Architecture

Research Notebook is a local research workbench running on native Windows 11. It ingests documents, stores them locally, ranks chunks through an embedded vector store, and synthesizes answers with the Agnes AI API.

## System overview

The application has five main components:

1. Web interface (`app.py`): Streamlit dashboard with four tabs: Notebook, Sources, Ask, and Brief.
2. Source storage (`sources_manager.py`): JSON Lines file storage at `data/sources/sources.jsonl`. Supports text paste, PDF via PyMuPDF/pypdf, plain text, Markdown, and web scraping.
3. Vector index and packer (`src/pack.py`): Local embedded Qdrant database at `data/qdrant` with local embeddings (`BAAI/bge-small-en-v1.5`).
4. Model client (`src/agnes_client.py` & `client.py`): OpenAI SDK client configured for Agnes AI (`https://apihub.agnes-ai.com/v1`) with optional OpenAI and Google fallbacks.
5. Synthesis engine (`synthesis.py`): Grounded question answering, citations list extraction, and research brief generation. Caches recent runs to `data/cache/last_ask.json` and `data/cache/last_brief.md`.

```
[User Input] (PDF / TXT / MD / URL / Paste)
       │
       ▼
[sources_manager.py] ──> data/sources/sources.jsonl
       │
       ▼
  [src/pack.py] (Chunking: 700 chars, 100 overlap)
       │
       ▼
 [Embedded Qdrant] ──> data/qdrant/ (Payload: {source_id, chunk_id, text})
       │
       ├── Query Ranking (Cosine similarity via BAAI/bge-small-en-v1.5)
       ▼
[Context Window Packer] (Respects character budget slider)
       │
       ├── Optional Web Snippets (Max 3, labeled web:, default OFF)
       ▼
 [synthesis.py] ──> Agnes API (agnes-3.0-flash)
       │
       ├── Ask tab (Answers with [source_id: "quote"] + citations list ──> data/cache/last_ask.json)
       └── Brief tab (Structured markdown saved to data/briefs/ and data/cache/last_brief.md)
```

## Data ingestion

Users add text through the Sources tab using three methods:
- Direct text pasting.
- File uploads for PDF, plain text, and Markdown files. PDF extraction uses PyMuPDF (`fitz`) with a `pypdf` fallback.
- Web URL fetching. The scraper fetches HTML and extracts text with `BeautifulSoup`.

Each record gets a UUID, title, source type, timestamp, character count, and token estimate (`chars // 4`). Records append to `data/sources/sources.jsonl`.

## Chunking and Qdrant payload schema

`src/pack.py` splits source documents into overlapping chunks. Default chunk size is 700 characters with a 100-character overlap.

Chunks are indexed in embedded Qdrant using `qdrant-client` with `path="data/qdrant"`. No external server or Docker container is used. Embeddings come from `fastembed` using the `BAAI/bge-small-en-v1.5` model, generating 384-dimensional dense vectors.

Every point in Qdrant contains the following payload schema:
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

When a user submits a query:
1. The query text is converted to a 384-dimensional dense vector.
2. Qdrant performs cosine similarity search against indexed chunks.
3. Chunks are returned sorted by similarity score.

## Context window packing and the 512K model limit

The default model, `agnes-3.0-flash`, accepts up to 512,000 tokens in its context window. However, relying on the model window alone fails when users upload extensive collections of papers or long reference documents.

Several practical limits make selective packing necessary:
1. Volume: A dozen full-length academic papers or technical manuals easily total 2,000,000 characters (roughly 500,000 tokens). Adding more files exceeds even a 512K window.
2. Quality: Large context windows suffer from attention degradation when irrelevant text dilutes relevant evidence. Placing hundreds of pages of unranked context into the prompt increases the risk of missed details.
3. Cost and latency: Passing hundreds of thousands of tokens per prompt increases inference time and API resource consumption.

To solve this, `src/pack.py` ranks chunks by similarity and packs only the top-scoring passages until it reaches the user-selected character budget cap. The slider in the sidebar lets the user configure this cap between 4,000 and 2,000,000 characters. Token counts are estimated as character count divided by 4.

## Web search isolation (default OFF)

The application includes an optional web search toggle in the sidebar, defaulted to **OFF**. When active, queries run through DuckDuckGo via the `ddgs` library.

The web module has two safety limits:
- It returns at most 3 snippets.
- Results are labeled `web:` in the prompt and UI.

Web results are never written to `data/sources/sources.jsonl` and never indexed in Qdrant. This keeps the primary document collection isolated from third-party web content.

## Model provider configuration

`src/agnes_client.py` uses the official `openai` Python SDK. It reads configuration from environment variables:
- Default: `AGNESAI_API_KEY` with base URL `https://apihub.agnes-ai.com/v1` and model `agnes-3.0-flash`.
- Optional: `OPENAI_API_KEY` and `OPENAI_BASE_URL` for OpenAI models (`gpt-5.6-luna`, `gpt-5.6-terra`).
- Optional: `GOOGLE_API_KEY` for Google models (`gemini-3.5-flash-l`).

If an optional environment variable is absent, the corresponding provider is excluded from the UI dropdown.
