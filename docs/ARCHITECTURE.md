# Architecture

Research Notebook runs as one native Windows Streamlit process. It keeps sources and Qdrant local, adds web results only when requested, and uses Agnes AI for generation.

## Data flow

```text
Paste / TXT / MD ───────────────┐
                                ├─> src/ingest.py ─> data/sources/<source_id>.json
PDF ─> pdf-inspector ─> routing ┘                         │
                                                          ▼
                                      chunk (~1000 chars, 150 overlap)
                                                          │
                                                          ▼
                                      embedded Qdrant: data/qdrant
                                                          │
Question ─> retrieve top k ─> pack uploaded chunks to character budget
                                                          │
Optional DDGS, OFF by default ─> append up to 3 web snippets last
                                                          │
                           src/ask.py or src/brief.py ─> Agnes AI
```

## Components

- `app.py`: Health, Sources, Notebook, Ask, and Brief pages plus sidebar controls.
- `src/ingest.py`: individual source JSON persistence, PDF/TXT/MD extraction, Qdrant upsert, counts, and deletion.
- `src/pdf_engine.py`: `pdf_inspector.process_pdf` inspection and optional Ollama OCR routing.
- `src/pack.py`: deterministic 384-dimensional local hash vectors, Qdrant retrieval, and character-budget packing.
- `src/web_search.py`: DDGS search returning at most three `origin=web` hits or an error string.
- `src/ask.py`: evidence-only Agnes prompt, citation verification, and `last_ask.json` persistence.
- `src/brief.py`: grounded four-section Markdown brief generation and persistence.
- `src/agnes_client.py`: official OpenAI SDK client, Agnes base URL, model, and HTTP 429 retry handling.

## Source storage

Each source is stored at `data/sources/<source_id>.json` with these core fields:

```json
{
  "id": "uuid",
  "title": "Paper title",
  "text": "Extracted or pasted text",
  "origin": "upload"
}
```

PDF sources additionally store `pdf_type` and `route` so the Sources page can display the inspection decision. Web results are never written here.

## Qdrant

Embedded Qdrant uses `path="data/qdrant"` and collection `sources`. One process must own the path. Every point includes at least:

```json
{
  "source_id": "uuid",
  "chunk_id": "uuid_0",
  "text": "Chunk text",
  "origin": "upload"
}
```

The query uses the same deterministic local hash function. Qdrant returns the top `k` candidates. The packer adds uploaded chunks in score order until it reaches the character budget, then returns the packed text and `{source_id, chunk_id}` entries.

If web search is enabled, web snippets are appended only after uploaded chunks under a separate `origin=web` header. They are not Qdrant points.

## Generation

The official `openai` SDK targets:

- Base URL: `https://apihub.agnes-ai.com/v1`
- Model: `agnes-3.0-flash`
- Key: Windows user environment variable `AGNESAI_API_KEY`

Ask tells Agnes to use packed evidence only and verifies quoted citations against retrieved chunk text. Brief uses these headings:

```markdown
## Claims
## Evidence
## Gaps
## Follow-ups
```

## Runtime boundaries

- Native Windows 11 only; no WSL2 or Docker.
- No remote vector database or downloaded embedding model.
- Web search defaults to OFF.
- `pdf-inspector` runs locally and is unrelated to Firecrawl Cloud.
- Ollama is contacted only for health checks or a PDF routed to OCR.

For implementation entry points and verification guidance, see the
[Developer Guide](DEVELOPER_GUIDE.md).
