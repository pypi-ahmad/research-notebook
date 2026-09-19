# Research Notebook

Research Notebook is a desktop research assistant built with Streamlit for native Windows 11. It lets you collect reference materials, rank relevant passages with an embedded vector index, and run grounded question answering and synthesis briefs using the Agnes AI API.

## Requirements

- Windows 11 (native execution, no WSL2 or Docker required)
- Python 3.14 or 3.13
- An Agnes AI API key set as the `AGNESAI_API_KEY` user environment variable

## Quick start

1. Open the repository at `D:\AI\Github\research-notebook`.
2. Ensure `AGNESAI_API_KEY` is set in your user environment variables, or create a `.env` file from `.env.example`.
3. Double-click `run.cmd` in Windows Explorer, or run it from PowerShell:

```cmd
run.cmd
```

On first launch, `run.cmd` verifies your `.env` configuration, creates a `.venv` virtual environment with `py -3`, installs packages from `requirements.txt`, and starts the Streamlit interface at `http://localhost:8501`.

## Navigation and workflow

The interface is organized into four tabs:

- Notebook: Shows storage statistics, context packing metrics, budget utilization, and the embedded Qdrant sync status.
- Sources: Ingests reference materials. Supports direct text pasting, file uploads (PDF via PyMuPDF/pypdf, plain text, Markdown), and web page scraping via URL. Records are stored as JSON Lines in `data/sources/sources.jsonl`.
- Ask: Answers user queries using ranked Qdrant chunks. Every answer pairs assertions with verbatim quotes and explicit source IDs in `[source_id: "quote"]` format, accompanied by an explicit citations list.
- Brief: Generates structured synthesis briefs containing claims, evidence citations, identified gaps, and follow-up actions. Briefs are saved as Markdown files under `data/briefs/` and cached at `data/cache/last_brief.md`.

## Context packing and the budget slider

The default model, `agnes-3.0-flash`, advertises a 512,000 token context window. Even with this large capacity, context packing remains essential.

When you import multiple technical papers, PDFs, or books into the application, raw character counts quickly exceed two million (over 500,000 tokens). In addition, dumping unranked context into a prompt causes lost-in-the-middle degradation where the model overlooks critical facts.

Research Notebook provides a character budget slider in the sidebar (configurable from 4,000 to 2,000,000 characters). When querying:
1. `src/pack.py` uses embedded Qdrant with `BAAI/bge-small-en-v1.5` embeddings to rank every source chunk by cosine similarity to your query.
2. The packer collects the highest-scoring chunks until the character cap is reached.
3. Estimated tokens are calculated and labeled as `chars // 4 (estimate)`.
4. Only relevant chunks enter the prompt, keeping the context dense and within safe token bounds.

## Optional web search (default OFF)

A sidebar checkbox lets you toggle DuckDuckGo web search. The web search module is **default OFF**.

When enabled, the search module runs in an isolated pipeline:
- It returns at most 3 snippets.
- Results are appended to the prompt under the strict `web:` prefix.
- Web snippets are never saved to `data/sources/` and never written to Qdrant.

This isolation guarantees external web text cannot pollute your canonical uploaded source index.

## Directory structure

```
research-notebook/
├── app.py                 # Streamlit application with Notebook/Sources/Ask/Brief tabs
├── client.py              # Root provider discovery alias
├── sources_manager.py     # Source loading, extraction (PyMuPDF/pypdf), and JSONL persistence
├── synthesis.py           # Grounded Q&A, citations list, and brief synthesis
├── web_search.py          # Isolated DuckDuckGo search module (default OFF)
├── run.cmd                # One-click Windows 11 launcher
├── requirements.txt       # Python dependencies
├── STATUS.md              # Implementation and verification log
├── src/
│   ├── __init__.py
│   ├── agnes_client.py    # Agnes AI client configuration (agnes-3.0-flash)
│   └── pack.py            # Embedded Qdrant chunk ranking and context packer
├── docs/
│   ├── ARCHITECTURE.md    # System architecture, Qdrant payload schema, and data flow
│   └── CITATIONS.md       # Quote span structure and verification guide
└── data/
    ├── briefs/            # Saved markdown research briefs
    ├── cache/             # Saved last_ask.json and last_brief.md
    ├── fixtures/          # Test reference documents (paper_a.txt, paper_b.txt)
    ├── qdrant/            # Local embedded Qdrant vector database
    └── sources/           # Canonical JSONL source records (sources.jsonl)
```

## Running tests

Run the end-to-end smoke test suite from PowerShell:

```powershell
.\.venv\Scripts\python.exe tests/smoke_e2e.py
```

The test loads fixtures (`paper_a.txt`, `paper_b.txt`), indexes chunks in embedded Qdrant with payload `{source_id, chunk_id, text}`, verifies an Ask query only `paper_a` answers, confirms `data/cache/last_ask.json` and `data/cache/last_brief.md` exist, and validates the optional Web ON path with `web:` labels.
