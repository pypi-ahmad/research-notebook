# Status

Local implementation status, 2026-09-20.

## Implemented

- Native Windows `run.cmd` setup and Streamlit launch.
- Agnes AI through the official OpenAI SDK with environment-only API key handling.
- Individual JSON source records and embedded Qdrant collection `sources`.
- Approximate 1,000-character chunks with 150-character overlap.
- Budgeted top-k retrieval with `{source_id, chunk_id}` provenance.
- Ask answers that use packed evidence and four-section Markdown briefs.
- DDGS search, off by default, with at most three separate `web:` snippets.
- Local `pdf-inspector` inspection and optional Ollama OCR through `pypdfium2` PNGs.
- PDF type and route display on the Sources page.

## Cache files present

The following files currently exist under `data/cache/`:

| File | Current content |
|---|---|
| `last_ingest.json` | Two Riverstone text source IDs and one Qdrant point per source |
| `last_ask.json` | Two grounded fixture answers: melting temperature and mining location |
| `last_brief.md` | Latest brief with Claims, Evidence, Gaps, and Follow-ups |
| `last_web.json` | Latest DDGS smoke result with up to three `origin=web` hits or an error |
| `pdf_optional.json` | `skipped`; `data/fixtures/text.pdf` is not present |

Runtime cache files are ignored by Git and later runs can replace them.

## Latest verification

- `scripts/smoke_ingest.py`: passed; text fixtures indexed.
- `scripts/smoke_ask.py`: passed; 812 cited paper A and Hale County cited paper B.
- `scripts/smoke_web.py`: passed; web results stayed separate from uploaded sources.
- `scripts/smoke_pdf_optional.py`: passed with expected skip because `text.pdf` is absent.
- `tests/smoke_test.py`: passed 7/7.
- Streamlit `AppTest`: loaded without exceptions; Web remains OFF by default.
