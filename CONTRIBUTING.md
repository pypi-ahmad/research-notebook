# Contributor runbook

This runbook is for changes to the Windows-native Research Notebook. For a
guided explanation of the code and a first end-to-end workflow, read the
[Developer Guide](docs/DEVELOPER_GUIDE.md).

## Before you change anything

- Work from `D:\AI\Github\research-notebook` on native Windows. Do not use
  WSL2 or Docker for this project.
- Run one process against `data/qdrant` at a time. Close Streamlit, smoke
  scripts, or other tools using that directory before running another Qdrant
  operation.
- Keep `AGNESAI_API_KEY` in the Windows user environment. Do not print it,
  put it in source files, or commit it.
- Web search stays off unless the caller explicitly enables it. Web results
  are supplementary `web:` snippets, never uploaded sources.

## Set up a local copy

Run this from the repository root:

```cmd
run.cmd
```

If `.env` does not exist, the launcher creates it from `.env.example`, opens
Notepad, and exits. Run `run.cmd` again after that. The launcher creates
`.venv`, installs `requirements.txt`, stops the process listening on port
8591, and starts Streamlit at `http://localhost:8591`.

On the Health page, check only whether the Agnes key is set. Do not paste a
key into the UI or a terminal transcript.

## Choose the right change location

| Change | Primary location | Keep this contract |
|---|---|---|
| Paste, TXT, Markdown, or PDF ingestion | `src/ingest.py`, `src/pdf_engine.py` | Store one JSON source record and synchronize its Qdrant points. |
| Chunking, embeddings, retrieval, or context budget | `src/pack.py` | Return `{source_id, chunk_id}` provenance and append web snippets last. |
| Grounded answers | `src/ask.py` | Use packed evidence only; validate source quotes against retrieved text. |
| Structured briefs | `src/brief.py` | Keep Claims, Evidence, Gaps, and Follow-ups in that order. |
| Agnes client or rate-limit behavior | `src/agnes_client.py` | Use the official OpenAI SDK, Agnes endpoint, and 429-only retry. |
| Optional search | `src/web_search.py` | Return no more than three normalized `origin="web"` hits or an error string. |
| Streamlit controls and pages | `app.py` | Keep Web off by default and label token values as estimates. |

The root `sources_manager.py`, `synthesis.py`, and `web_search.py` are
compatibility surfaces. Do not move new runtime behavior into them unless the
task requires a legacy caller or test.

## Make a safe change

1. Start with the relevant public docstring and its callers.
2. Preserve the local-only source path: source JSON, embedded Qdrant, packed
   evidence, then Agnes generation.
3. For PDF work, call `pdf_inspector.process_pdf`. Do not use `fitz`,
   PyMuPDF, PaddlePaddle, or `process_pdf_with_ocr`.
4. OCR is optional. Use local Ollama only for a PDF routed to OCR, render pages
   with `pypdfium2`, and continue with native text if Ollama or its model is
   unavailable.
5. Add or update Google-style docstrings for public Python interfaces. Cover
   inputs, outputs, visible side effects, and meaningful failures.

## Verify the affected path

Run the narrowest useful command first. The commands below are run from the
repository root.

| Change | Command | Expected result |
|---|---|---|
| Any Python change | `.venv\Scripts\python tests\smoke_test.py` | Seven checks pass without an Agnes request. |
| Ingestion or Qdrant change | `.venv\Scripts\python scripts\smoke_ingest.py` | Riverstone sources and Qdrant point counts are written to `data/cache/last_ingest.json`. |
| Ask or Brief change | `.venv\Scripts\python scripts\smoke_ask.py` | `812` cites paper A and Hale County cites paper B, with Web off. |
| Web change | `.venv\Scripts\python scripts\smoke_web.py` | A cache record contains no more than three hits or a handled error. |
| PDF or OCR change | `.venv\Scripts\python scripts\smoke_pdf_optional.py` | A PDF result is recorded, or the missing fixture records `skipped`. |

Also compile the Python files you changed and check the diff:

```powershell
Get-ChildItem app.py, src\*.py, scripts\*.py |
  ForEach-Object { .venv\Scripts\python.exe -m py_compile $_.FullName }
git diff --check
```

## Troubleshooting

| Symptom | What to do |
|---|---|
| Qdrant path is locked | Close other processes using `data/qdrant`, then rerun the command. |
| Health says the Agnes key is unavailable | Set `AGNESAI_API_KEY` in the Windows user environment, open a new terminal, and restart Streamlit. |
| OCR pages are skipped | Start Ollama and install the configured model, or keep the available native text and use the warning to explain the gap. |
| DDGS search fails | Keep Web off for source-only work. With Web on, the returned error is an expected handled result. |
| A claim lacks a citation | Check the packed chunks first. If they do not contain the answer, Ask must say so rather than infer it. |

## Documentation map

- [README](README.md): installation and product boundaries.
- [Developer Guide](docs/DEVELOPER_GUIDE.md): onboarding and zero-to-mastery tutorial.
- [Architecture](docs/ARCHITECTURE.md): active data flow and storage contracts.
- [Citations](docs/CITATIONS.md): uploaded-source versus `web:` evidence.
- [PDF and OCR](docs/PDF_AND_OCR.md): local routing and OCR behavior.
