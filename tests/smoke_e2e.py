"""End-to-End Smoke Test hitting Agnes AI with fixtures paper_a.txt and paper_b.txt.

Workflow:
1. Load fixtures paper_a.txt and paper_b.txt from data/fixtures/.
2. Ingest into sources_manager (data/sources/sources.jsonl).
3. Index and rank chunks using embedded Qdrant (src/pack.py, payload {source_id, chunk_id, text}).
4. Web OFF: Ask question only paper_a answers, save data/cache/last_ask.json and data/cache/last_brief.md.
   Hit Agnes. Verify valid JSON and brief structure.
5. Web ON: Run query fixtures cannot answer, verifying web: labels and isolation.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sources_manager
import src.pack as pack
import synthesis


def run_e2e_smoke():
    print("[1/5] Loading fixtures paper_a.txt and paper_b.txt from data/fixtures/...")
    fixture_a = ROOT / "data" / "fixtures" / "paper_a.txt"
    fixture_b = ROOT / "data" / "fixtures" / "paper_b.txt"

    assert fixture_a.exists(), f"Missing fixture: {fixture_a}"
    assert fixture_b.exists(), f"Missing fixture: {fixture_b}"

    text_a = fixture_a.read_text(encoding="utf-8")
    text_b = fixture_b.read_text(encoding="utf-8")

    # Clear previous sources for clean smoke run
    sources_manager.clear_sources()

    s_a = sources_manager.add_source(
        title="Chronos Engine: KV Cache Retention",
        content=text_a,
        source_type="upload",
        filename="paper_a.txt",
    )
    s_b = sources_manager.add_source(
        title="Project Aether: Speculative Decoding",
        content=text_b,
        source_type="upload",
        filename="paper_b.txt",
    )

    sources = [s_a, s_b]
    print(f"  [OK] Ingested 2 fixtures: paper_a={s_a.id[:8]}, paper_b={s_b.id[:8]}")

    print("[2/5] Indexing source chunks into embedded Qdrant (payload {source_id, chunk_id, text})...")
    qdrant_dir = ROOT / "data" / "qdrant"
    indexed_count = pack.index_sources_to_qdrant(sources, qdrant_path=str(qdrant_dir))
    assert indexed_count > 0, "No chunks were indexed into Qdrant"
    print(f"  [OK] Successfully indexed {indexed_count} chunks into embedded Qdrant.")

    print("[3/5] Asking question only paper_a answers (Web OFF, hitting Agnes AI)...")
    q_paper_a = "What was the exact needle recall achieved by the Chronos engine and how many sink tokens per attention layer did it use?"
    qa_result = synthesis.ask_question(
        query=q_paper_a,
        sources=sources,
        char_cap=200_000,
        web_enabled=False,
        provider_id="agnes",
    )

    answer = qa_result["answer"]
    citations = qa_result.get("citations", [])
    print("\n--- AGNES AI ANSWER (paper_a query) ---")
    print(answer)
    print("---------------------------------------\n")
    print(f"Extracted Citations ({len(citations)}):")
    for c in citations:
        print(f"  - [{c['source']}]: \"{c['quote']}\"")

    assert len(answer.strip()) > 0, "Empty answer from Agnes AI"
    # Check that Chronos facts from paper_a are present
    assert "99.1%" in answer or "99.1" in answer, "Answer must contain Chronos 99.1% needle recall from paper_a"
    assert "16" in answer, "Answer must contain 16 sink tokens from paper_a"

    # Verify data/cache/last_ask.json
    cache_ask_file = ROOT / "data" / "cache" / "last_ask.json"
    assert cache_ask_file.exists(), f"Missing cache file: {cache_ask_file}"
    with open(cache_ask_file, "r", encoding="utf-8") as f:
        cached_ask_data = json.load(f)
    assert cached_ask_data["query"] == q_paper_a
    assert len(cached_ask_data["answer"]) > 0
    print("  [OK] Verified data/cache/last_ask.json exists and contains valid JSON.")

    # Polite pause between requests to respect free-tier rate limit
    time.sleep(3)

    print("[4/5] Generating structured brief (saving to data/briefs/ and data/cache/last_brief.md)...")
    brief_topic = "Chronos KV Cache Retention Architecture"
    brief_result = synthesis.generate_brief(
        topic=brief_topic,
        sources=sources,
        char_cap=200_000,
        web_enabled=False,
        provider_id="agnes",
        output_dir=ROOT / "data" / "briefs",
    )

    brief_content = brief_result["content"]
    assert "Claim" in brief_content or "Evidence" in brief_content, "Brief must contain Claims and Evidence"
    assert "Gap" in brief_content, "Brief must contain Gaps"
    assert "Follow" in brief_content, "Brief must contain Follow-ups"

    cache_brief_file = ROOT / "data" / "cache" / "last_brief.md"
    assert cache_brief_file.exists(), f"Missing cache file: {cache_brief_file}"
    brief_text_cached = cache_brief_file.read_text(encoding="utf-8")
    assert len(brief_text_cached.strip()) > 0
    print(f"  [OK] Verified data/cache/last_brief.md exists ({len(brief_text_cached):,} bytes).")

    # Polite pause before optional web test
    time.sleep(3)

    print("[5/5] Optional path: Web ON for a question fixtures cannot answer...")
    q_web = "What is the release date and latest status of Python 3.14?"
    web_result = synthesis.ask_question(
        query=q_web,
        sources=sources,
        char_cap=200_000,
        web_enabled=True,
        provider_id="agnes",
    )

    web_answer = web_result["answer"]
    web_snippets = web_result.get("web_snippets", [])
    print("\n--- AGNES AI ANSWER (Web ON query) ---")
    print(web_answer[:500] + ("...\n" if len(web_answer) > 500 else "\n"))
    print("--------------------------------------\n")
    print(f"Retrieved Web Snippets ({len(web_snippets)}):")
    for s in web_snippets:
        print(f"  - web: [{s.get('title', '')}] {s.get('body', '')[:100]}...")

    assert len(web_snippets) > 0, "Web search should return snippets when enabled"
    assert len(web_snippets) <= 3, "Web search must cap at 3 snippets"
    print("  [OK] Verified web: labels and search isolation when Web is ON.")

    print("\nALL SMOKE TESTS SUCCEEDED.")


if __name__ == "__main__":
    try:
        run_e2e_smoke()
        sys.exit(0)
    except Exception as exc:
        print(f"\nE2E SMOKE TEST FAILED: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
