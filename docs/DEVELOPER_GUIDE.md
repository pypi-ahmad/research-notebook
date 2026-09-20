# Developer Guide

This guide covers local setup, source ingestion, retrieval, grounded
generation, web search, and PDF/OCR work for contributors on Windows.

Use the [Contributor runbook](../CONTRIBUTING.md) when you already know the
area you are changing and need a short implementation and verification
checklist. This guide is the longer onboarding and learning path.

## Application map

The active application path is:

```text
app.py -> src.ingest -> data/sources/<source_id>.json -> src.pack/Qdrant
       -> src.ask or src.brief -> Agnes AI
```

`sources_manager.py`, root `synthesis.py`, and root `web_search.py` are
compatibility surfaces. They support older callers and tests; new runtime work
belongs in `src/` unless the task explicitly requires compatibility behavior.

## 1. Set up and launch

### Prerequisites

- Windows 11 with `py -3` available.
- `AGNESAI_API_KEY` in the Windows user environment for Ask and Brief.
- Optional local Ollama only for OCR-routed PDFs or the Health-page model list.

Do not put the Agnes key in Git, source files, or `.env`. `run.cmd` creates
`.env` from `.env.example` as a local setup cue, but the application reads the
key from the Windows process environment.

### First run

From the repository root:

```cmd
run.cmd
```

If `.env` is missing, the command copies `.env.example`, opens Notepad, and
exits. Run the same command again. It creates `.venv`, installs requirements,
stops the process listening on port 8591, and starts Streamlit at
`http://localhost:8591`.

On Health, confirm that the Agnes key is
set; never paste or log the key.

## 2. Zero-to-mastery path

### Step 1: Learn the local source path

Run the text-only ingestion smoke:

```cmd
.venv\Scripts\python scripts\smoke_ingest.py
```

It loads the Riverstone fixtures, writes individual source records under
`data/sources/`, upserts their chunks to embedded Qdrant, and records source
IDs and point counts in `data/cache/last_ingest.json`.

Read `src/ingest.py` before changing source persistence. A source JSON record
has `id`, `title`, `text`, and `origin`. PDF records also retain `pdf_type` and
`route`.

### Step 2: Understand retrieval and packed context

`src/pack.py` creates deterministic local hash vectors, retrieves the sidebar
top-`k` Qdrant candidates, then adds uploaded chunks until the character budget
is reached. The returned citation list contains `{source_id, chunk_id}` pairs.

Use the Notebook page to inspect the broader whole-source summary. Use
`rank_and_pack_chunks` for Ask and Brief retrieval behavior. Do not open a
second process against `data/qdrant`; embedded Qdrant allows one owner.

### Step 3: Verify grounded generation

With `AGNESAI_API_KEY` set, run:

```cmd
.venv\Scripts\python scripts\smoke_ask.py
```

This live Agnes check expects the melting-point answer to cite the source
containing `812 C` and the mining answer to cite the separate Hale County
source. It writes `last_ask.json` and `last_brief.md` under `data/cache/`.

When changing `src/ask.py`, preserve the evidence-only prompt contract and
verify citations against retrieved chunk text. When changing `src/brief.py`,
preserve these headings in order:

```markdown
## Claims
## Evidence
## Gaps
## Follow-ups
```

### Step 4: Work on optional web augmentation

Web search is OFF by default. When enabled, `src.web_search.search_web` returns
at most three dictionaries containing `title`, `href`, `text`, and
`origin="web"`, or an empty list and error string on failure. `src.pack` places
web snippets after uploaded chunks and does not index them.

Run the network-dependent smoke when changing this path:

```cmd
.venv\Scripts\python scripts\smoke_web.py
```

The script writes `data/cache/last_web.json` whether DDGS returns hits or a
handled error.

### Step 5: Work on PDF and OCR routing

Start with [PDF and OCR](PDF_AND_OCR.md). `pdf_inspector.process_pdf` supplies
native Markdown and page routing information. `src.pdf_engine` invokes local
Ollama only for OCR-routed pages; it renders pages with `pypdfium2` and sends
PNG data through the Ollama `images` field with prompt `OCR:`.

Run the optional smoke:

```cmd
.venv\Scripts\python scripts\smoke_pdf_optional.py
```

It records a skip if `data/fixtures/text.pdf` is absent. A scanned fixture and
an installed Ollama model are not required for ordinary development.

## 3. Public Python interfaces

| Module | Primary public interface | Contract |
|---|---|---|
| `src.ingest` | `ingest_text`, `ingest_upload`, `load_sources`, `delete_source` | Persists individual source JSON records and synchronizes their Qdrant points. |
| `src.pack` | `index_sources_to_qdrant`, `rank_and_pack_chunks` | Stores chunks, retrieves top candidates, packs to a character budget, and returns provenance. |
| `src.ask` | `ask_question` | Produces an evidence-only Agnes answer and writes `last_ask.json`. |
| `src.brief` | `generate_brief` | Produces a four-section Markdown brief and writes timestamped/cache files. |
| `src.pdf_engine` | `process_pdf_document` | Returns native/OCR Markdown, PDF classification, selected route, and warnings. |
| `src.web_search` | `search_web` | Returns `(hits, error)` without raising expected library/network failures. |
| `src.agnes_client` | `build_client`, `call_chat_completion_with_retry` | Creates the OpenAI-compatible Agnes client and retries HTTP 429 responses. |

Read the Google-style docstrings before changing these interfaces. They cover
parameters, return values, side effects, and errors.

## 4. Verification runbook

| Command | External dependency | What it verifies |
|---|---|---|
| `.venv\Scripts\python tests\smoke_test.py` | No Agnes request; expects the Agnes key to be present | Imports, mocked retry, PDF routing, fixtures, and app compilation. |
| `.venv\Scripts\python scripts\smoke_ingest.py` | Local Qdrant | Fixture ingestion and point counts. |
| `.venv\Scripts\python scripts\smoke_ask.py` | Agnes API | Grounded Ask answers and Brief headings with Web OFF. |
| `.venv\Scripts\python scripts\smoke_web.py` | DDGS network and local Qdrant | Normalized web hits/errors and web-last packing. |
| `.venv\Scripts\python scripts\smoke_pdf_optional.py` | Optional local Ollama only if a routed fixture needs OCR | Optional PDF inspection or expected skip. |

`tests/smoke_e2e.py` uses retained JSONL compatibility paths. It is not the
default acceptance path for the active individual-JSON source workflow.

After Python changes, also run this PowerShell check:

```powershell
Get-ChildItem app.py, src\*.py, scripts\*.py |
  ForEach-Object { .venv\Scripts\python.exe -m py_compile $_.FullName }
git diff --check
```

If Qdrant reports a lock, close other applications or scripts using
`data/qdrant`, then rerun the affected command.

## 5. Documentation maintenance

### Current audit scope

This pass covers 46 public classes and functions across root runtime modules,
`src/`, and `scripts/`; all have docstrings. Test functions and private helpers
are outside the coverage scope. User-facing Markdown describes individual
source JSON as the active storage format. JSONL references remain in
compatibility code and its legacy smoke path.

Use Google-style docstrings for public functions and classes:

- Start with a plain-language summary.
- Add `Args`, `Returns`, and `Raises` when the public contract has inputs,
  output, or meaningful failure behavior.
- Document externally visible side effects such as source persistence, cache
  writes, Qdrant upserts, network requests, or model calls.
- Keep private helpers and obvious data properties concise.

Keep user-facing docs synchronized with verified code:

- [Architecture](ARCHITECTURE.md) explains active data flow and boundaries.
- [Citations](CITATIONS.md) distinguishes uploaded `source_id` evidence from
  auxiliary `web:` snippets.
- [PDF and OCR](PDF_AND_OCR.md) explains local inspection and optional OCR.
- [Status](../STATUS.md) records current cache artifacts and completed checks.

Before submitting documentation, check relative links, commands, and claims
against the current source. Do not describe an API call, fixture, or validation
result that has not been verified.
