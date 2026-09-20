# Long-context Research Notebook

A native Windows 11 Streamlit app for collecting sources, finding relevant passages in embedded Qdrant, and writing grounded answers and research briefs with Agnes AI.

## Run on Windows

Set `AGNESAI_API_KEY` as a Windows user environment variable. The app reads the key from the process environment and never writes or displays it.

From `D:\AI\Github\research-notebook`, run:

```cmd
run.cmd
```

On the first run, if `.env` is absent, `run.cmd` copies `.env.example`, opens it in Notepad, and exits. Run `run.cmd` again to execute:

```cmd
py -3 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\streamlit run app.py --server.port=8591
```

The `.env.example` file contains variable names only. Keep `AGNESAI_API_KEY` in the Windows user environment, not in `.env`, source files, or Git.

The launcher uses `http://localhost:8591`. Before it starts the app, it stops
the process currently listening on port 8591 so a repeat launch restarts the
notebook cleanly.

## Workflow

- Health reports whether the Agnes key is set and can list local Ollama models.
- Sources accepts pasted text and PDF, TXT, or Markdown uploads. Each upload is stored in its own JSON file under `data/sources/`.
- Notebook shows source and context-budget statistics.
- Ask retrieves Qdrant chunks, packs them within the selected character budget, and asks `agnes-3.0-flash` to answer from that evidence.
- Brief creates Markdown with Claims, Evidence, Gaps, and Follow-ups.

Token counts shown in the UI are estimates calculated as `chars / 4`.

## Local Qdrant

The app uses embedded `qdrant-client` storage at `data/qdrant`, collection `sources`. Embedded Qdrant permits one process to use that path at a time. Close other scripts or apps using `data/qdrant` before starting another operation.

## Optional web search

Web search is off by default. When enabled, `ddgs` returns at most three snippets. The app appends them after uploaded chunks, labels them `web:`, and never saves or indexes them as sources. A library or network failure shows a warning and leaves the app running.

## PDF and optional OCR

PDF inspection uses the locally installed `pdf-inspector` Python package. It is not Firecrawl Cloud and does not send PDFs to Firecrawl.

Native PDFs use the Markdown returned by `pdf_inspector.process_pdf`. OCR runs only for PDFs routed to OCR when the configured Ollama service and model are available. It uses `pypdfium2` PNG pages and `AuditAid/PaddleOCR-VL-1.6-0.9B`. If Ollama or the model is unavailable, the app skips affected pages, retains native text, and shows a warning on Sources.

See [PDF_AND_OCR.md](docs/PDF_AND_OCR.md) for routing details.

## Development

For a short change-and-verify checklist, see the
[Contributor runbook](CONTRIBUTING.md). For setup, the zero-to-mastery
walkthrough, public Python interfaces, and troubleshooting, see the
[Developer Guide](docs/DEVELOPER_GUIDE.md).

## Verification scripts

```cmd
.venv\Scripts\python scripts\smoke_ingest.py
.venv\Scripts\python scripts\smoke_ask.py
.venv\Scripts\python scripts\smoke_web.py
.venv\Scripts\python scripts\smoke_pdf_optional.py
```

The PDF smoke is optional. If `data/fixtures/text.pdf` is absent, it records a skipped result instead of failing.

## Local data

Runtime data is stored under `data/` and ignored by Git:

- `data/sources/`: individual source JSON records
- `data/qdrant/`: embedded vector store
- `data/briefs/`: timestamped research briefs
- `data/cache/`: latest smoke and application artifacts
- `data/pages/`: temporary OCR page images
