# Status log

## Implementation prompt 1
- Timestamp: 2026-09-19T22:28:40+05:30
- Initialized `D:\AI\Github\research-notebook`.
- Added `run.cmd` launcher with `.env.example` copy and notepad prompt.
- Created Streamlit app layout with four tabs: Notebook, Sources, Ask, and Brief.
- Built `sources_manager.py` with JSONL persistence under `data/sources/sources.jsonl`.
- Implemented source ingestion for pasted text, uploaded PDF, TXT, MD, and URL scraping.
- Implemented context packing with character budget slider and token estimator (`chars // 4`).
- Added isolated `web_search.py` using DuckDuckGo search (`ddgs`), defaulted to off.
- Configured `client.py` for model routing with Agnes AI (`agnes-3.0-flash`, `https://apihub.agnes-ai.com/v1`) default and conditional OpenAI and Google options.
- Added `.gitignore` and `.env.example` with variable names only.

### Verification (prompt 1)
- Command: `.\.venv\Scripts\python.exe tests/smoke_test.py`
- Result: Passed. All 4 unit checks succeeded with zero external API calls.

## Implementation prompt 2
- Timestamp: 2026-09-19T22:56:30+05:30
- Created `src/pack.py` with chunk ranking using embedded Qdrant (`qdrant-client`, `path="data/qdrant"`) and context window packing.
- Created `synthesis.py`:
  - Ask queries ground assertions in ranked Qdrant chunks, citing verbatim quotes and explicit `[source_id: "quote"]`.
  - Brief generation creates structured markdown with claims, evidence lists, gaps, and follow-up actions saved to `data/briefs/`.
  - Web augmentation appends at most 3 snippets labeled `web:` without adding them to the uploaded source index.
- Created test fixtures: `data/fixtures/attention_scaling.txt` and `data/fixtures/retrieval_chunking.txt`.
- Updated `app.py` to connect vector sync, Ask citation flow, and Brief generation and download.
- Added `qdrant-client` and `fastembed` to `requirements.txt` and updated `run.cmd`.

### Verification (prompt 2)
- Command: `.\.venv\Scripts\python.exe tests/smoke_e2e.py`
- Result: Passed with exit code 0.
  - Ingested 2 fixtures into `data/sources/sources.jsonl`.
  - Indexed 4 chunks into embedded Qdrant (`data/qdrant`).
  - Queried Agnes AI (`agnes-3.0-flash`) and verified answer contained verbatim quotes and source ID citations.
  - Generated structured brief from Agnes AI and verified file written to `data/briefs/`.
  - Verified web snippet isolation and `web:` labeling.

## Implementation prompt 3
- Timestamp: 2026-09-19T22:58:30+05:30
- Added user documentation:
  - `README.md`: Quick start guide, tab navigation, 512K context packing warning, and directory layout.
  - `docs/ARCHITECTURE.md`: Data flow, embedded Qdrant indexing, and context window limits.
  - `docs/CITATIONS.md`: Quote span format, chunk metadata tracking, verification procedure, and web snippet isolation.
- Applied humanizer guidelines across all repository documentation to remove AI prose patterns, em dashes, and decorative formatting.

## Implementation prompt 4
- Timestamp: 2026-09-19T23:20:00+05:30
- Explicitly labeled all token counts as estimate (`chars // 4`) throughout `app.py`.
- Added backoff and retry handling (`call_chat_completion_with_retry`) in `synthesis.py` for API rate limits.
- Confirmed web search module is default off, uses DuckDuckGo, and appends snippets labeled `web:` without touching uploaded sources.
- Verified embedded Qdrant vector indexing at `data/qdrant` and context packing under the character budget cap.

### Verification (prompt 4)
- Command: `.\.venv\Scripts\python.exe tests/smoke_e2e.py`
- Result: Passed with exit code 0.

## Implementation prompt 5
- Timestamp: 2026-09-19T23:31:00+05:30
- Added `src/agnes_client.py` with Agnes AI (`agnes-3.0-flash`, `https://apihub.agnes-ai.com/v1`) default and conditional provider routing.
- Updated `requirements.txt` with all specified packages (`streamlit`, `openai`, `python-dotenv`, `pymupdf`, `qdrant-client`, `pandas`, `pydantic`, `httpx`, `ddgs`, `fastembed`, `beautifulsoup4`, `pypdf`).
- Created distinct fact fixtures: `data/fixtures/paper_a.txt` (Chronos KV cache retention, 99.1% recall, 16 sink tokens) and `data/fixtures/paper_b.txt` (Project Aether speculative decoding with FP4 quantization).
- Configured Qdrant upsert payload schema explicitly containing `{source_id, chunk_id, text}`.
- Updated `synthesis.py` to extract a structured citations list, save `data/cache/last_ask.json`, and cache `data/cache/last_brief.md`.
- Updated `app.py` Ask tab to render an explicit Grounded Citations List.
- Configured `web_search.py` to use `ddgs` library with clean fallback.
- Updated `README.md`, `docs/ARCHITECTURE.md`, `docs/CITATIONS.md`.

### Verification (prompt 5)
- Command: `.\.venv\Scripts\python.exe tests/smoke_e2e.py`
- Result: Passed with exit code 0.
  - Ingested fixtures `paper_a.txt` and `paper_b.txt` into `data/sources/sources.jsonl`.
  - Indexed 4 chunks into embedded Qdrant with payload `{source_id, chunk_id, text}`.
  - Web OFF query: Asked question only `paper_a` answers ("What was the exact needle recall achieved by the Chronos engine and how many sink tokens per attention layer did it use?"). Verified Agnes AI answer contained 99.1% and 16 sink tokens, with citations.
  - Verified `data/cache/last_ask.json` exists and contains valid JSON.
  - Synthesized structured brief, verified `data/cache/last_brief.md` exists and contains claims, evidence, gaps, and follow-ups.
  - Web ON query: Asked question fixtures cannot answer ("What is the release date and latest status of Python 3.14?"). Verified 3 web snippets retrieved with `web:` labels and isolated from source indices.
