"""End-to-End Smoke Test hitting Agnes AI with fixtures paper_a.txt and paper_b.txt.

Workflow:
1. Load fixtures paper_a.txt and paper_b.txt from data/fixtures/.
2. Ingest into sources_manager (data/sources/sources.jsonl).
3. Index and rank chunks using embedded Qdrant (src/pack.py, payload {source_id, chunk_id, text}).
4. Web OFF: Ask question only paper_a answers, save data/cache/last_ask.json and data/cache/last_brief.md.
   Hit Agnes. Verify valid JSON and brief structure.
5. Verify both named cache files exist. Web remains OFF for the full smoke.
"""

from __future__ import annotations

import json
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
    print("[1/4] Loading text fixtures with Web OFF...")
    fixture_a = ROOT / "data" / "fixtures" / "paper_a.txt"
    fixture_b = ROOT / "data" / "fixtures" / "paper_b.txt"

    assert fixture_a.exists(), f"Missing fixture: {fixture_a}"
    assert fixture_b.exists(), f"Missing fixture: {fixture_b}"

    text_a = fixture_a.read_text(encoding="utf-8")
    text_b = fixture_b.read_text(encoding="utf-8")

    # Clear previous sources for clean smoke run
    sources_manager.clear_sources()

    s_a = sources_manager.add_source(
        title="Riverstone Furnace Notes",
        content=text_a,
        source_type="upload",
        filename="paper_a.txt",
    )
    s_b = sources_manager.add_source(
        title="Riverstone Provenance Notes",
        content=text_b,
        source_type="upload",
        filename="paper_b.txt",
    )

    sources = [s_a, s_b]
    print(f"  [OK] Ingested 2 fixtures: paper_a={s_a.id[:8]}, paper_b={s_b.id[:8]}")

    print("[2/4] Indexing source chunks into embedded Qdrant collection 'sources'...")
    qdrant_dir = ROOT / "data" / "qdrant"
    indexed_count = pack.index_sources_to_qdrant(sources, qdrant_path=str(qdrant_dir))
    assert indexed_count > 0, "No chunks were indexed into Qdrant"
    print(f"  [OK] Successfully indexed {indexed_count} chunks into embedded Qdrant.")

    print("[3/4] Asking question only paper_a answers (Web OFF, hitting Agnes AI)...")
    q_paper_a = "At what temperature does Riverstone glass melt?"
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
        print(f'  - [{c["source"]}]: "{c["quote"]}"')

    assert len(answer.strip()) > 0, "Empty answer from Agnes AI"
    assert "812" in answer, "Answer must contain the Riverstone melting point"
    assert citations, "Answer must contain at least one verified source_id quote"

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

    print("[4/4] Generating structured brief with Web OFF...")
    brief_topic = "Riverstone glass facts"
    brief_result = synthesis.generate_brief(
        topic=brief_topic,
        sources=sources,
        char_cap=200_000,
        web_enabled=False,
        provider_id="agnes",
        output_dir=ROOT / "data" / "briefs",
    )

    brief_content = brief_result["content"]
    assert "Claim" in brief_content or "Evidence" in brief_content, (
        "Brief must contain Claims and Evidence"
    )
    assert "Gap" in brief_content, "Brief must contain Gaps"
    assert "Follow" in brief_content, "Brief must contain Follow-ups"

    cache_brief_file = ROOT / "data" / "cache" / "last_brief.md"
    assert cache_brief_file.exists(), f"Missing cache file: {cache_brief_file}"
    brief_text_cached = cache_brief_file.read_text(encoding="utf-8")
    assert len(brief_text_cached.strip()) > 0
    print(
        f"  [OK] Verified data/cache/last_brief.md exists ({len(brief_text_cached):,} characters)."
    )

    print("\nALL WEB-OFF E2E SMOKE TESTS SUCCEEDED.")


if __name__ == "__main__":
    try:
        run_e2e_smoke()
        sys.exit(0)
    except Exception as exc:
        print(f"\nE2E SMOKE TEST FAILED: {exc}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)
