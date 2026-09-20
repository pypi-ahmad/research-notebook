# PDF inspection and OCR

PDF handling is local and optional. You do not need a scanned PDF fixture to run or verify the application.

## Inspection

`src/pdf_engine.py` writes the uploaded bytes to a temporary local PDF and calls:

```python
pdf_inspector.process_pdf(path)
```

The implementation reads the installed package's result attributes, including `pdf_type`, `markdown`, `page_count`, `confidence`, and `pages_needing_ocr`.

`pdf-inspector` is a local Python package used by this project. This workflow does not upload PDFs to Firecrawl.

## Routing

- `native`: PDFs with usable native Markdown are ingested directly when they are not routed to OCR.
- `ollama`: Scanned or image-based PDFs, empty native Markdown, mixed PDFs with identified OCR pages, and PDFs processed with Force OCR route pages to OCR.

The Sources page displays the stored `pdf_type` and route for ingested PDFs.

## Ollama OCR

OCR runs only after a PDF is routed to it. The app first checks whether Ollama is reachable and the configured model exists.

Defaults:

```text
OLLAMA_HOST=http://localhost:11434
OLLAMA_OCR_MODEL=AuditAid/PaddleOCR-VL-1.6-0.9B
```

For each routed page:

1. `pypdfium2` renders a local PNG.
2. The PNG bytes are base64 encoded.
3. The Ollama generate request uses prompt `OCR:` and supplies the PNG through the `images` field.
4. Returned text is appended to any native Markdown with an OCR page marker.

The app does not install or download the Ollama model.

## Missing Ollama or model

If Ollama is down or the model is absent:

- Routed OCR pages are skipped.
- Any available native Markdown is still ingested.
- The UI shows a warning explaining that OCR pages were skipped.
- If no native or OCR text exists, the source is not saved and the UI reports that no text was ingested.

Failures on one OCR page do not stop processing of other pages.

## Optional smoke

Run:

```cmd
.venv\Scripts\python scripts\smoke_pdf_optional.py
```

If `data/fixtures/text.pdf` exists, the script records its inspection result. Otherwise it writes a successful skip record to `data/cache/pdf_optional.json`. A scanned PDF is not required.

For contributor workflows and troubleshooting, see the
[Developer Guide](DEVELOPER_GUIDE.md).
