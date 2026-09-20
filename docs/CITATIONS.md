# Citations

Research Notebook keeps uploaded-source evidence separate from optional web snippets.

## Uploaded sources: `source_id`

Every uploaded or pasted source receives a UUID. Qdrant chunks retain both the source and chunk identifiers:

```json
{
  "source_id": "887c2222-4050-4f56-be0e-a5c2e1bb5e95",
  "chunk_id": "887c2222-4050-4f56-be0e-a5c2e1bb5e95_0"
}
```

Ask answers cite factual claims with the actual source ID and a verbatim quote:

```text
Riverstone glass melts at 812 C [887c2222-4050-4f56-be0e-a5c2e1bb5e95: "Riverstone glass melts at 812 C under the documented test conditions"]
```

`src/ask.py` adds a citation to the structured citation list only when:

1. The cited `source_id` belongs to a packed chunk.
2. The quoted text occurs in that chunk.

Verified citations and the packed `{source_id, chunk_id}` list are written to `data/cache/last_ask.json`.

## Web snippets: `web:`

Web search is optional and OFF by default. A web result has this shape:

```json
{
  "title": "Result title",
  "href": "https://example.com/",
  "text": "Search snippet",
  "origin": "web"
}
```

Web-supported statements use `web:` instead of a UUID:

```text
[web: "verbatim text from the search snippet"]
```

Web snippets appear after uploaded chunks. They are never saved under `data/sources/`, assigned an uploaded `source_id`, or indexed in Qdrant.

## Interpretation

- `source_id` identifies evidence from a locally stored upload or pasted source.
- `web:` identifies evidence from an optional DDGS search snippet.
- Search snippets are supplementary evidence, not uploaded primary sources.
- When packed evidence lacks the answer, Ask says so instead of using model memory.

For the retrieval and verification workflow, see the
[Developer Guide](DEVELOPER_GUIDE.md).
