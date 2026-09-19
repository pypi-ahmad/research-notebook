"""Smoke test verifying imports, source manager, context packing, and client setup.

Per instructions: No LLM API calls are made in this test.
"""

import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import client
import sources_manager
import web_search


def test_client_configuration():
    print("[1/4] Testing client provider configuration...")
    providers = client.get_available_providers()
    print(f"  Detected active providers: {list(providers.keys())}")
    assert "agnes" in providers, "Agnes AI should be configured as default provider"
    agnes_info = providers["agnes"]
    assert agnes_info.default_model == "agnes-3.0-flash"
    assert "agnes-3.0-flash" in agnes_info.models
    assert agnes_info.base_url == "https://apihub.agnes-ai.com/v1"

    # Test client instantiation without network call
    c, model = client.build_client("agnes")
    assert c is not None
    assert model == "agnes-3.0-flash"
    print("  [OK] Agnes AI client instance verified without API call.")


def test_sources_and_context_packing():
    print("[2/4] Testing sources JSONL storage and Agnes 512K context packing...")
    test_file = ROOT / "data" / "sources" / "test_sources.jsonl"
    if test_file.exists():
        test_file.unlink()

    # Add items
    s1 = sources_manager.add_source(
        title="Sample Note A",
        content="Antigravity deep learning research notes.",
        source_type="paste",
        sources_file=test_file,
    )
    assert s1.char_count == len(s1.content)
    assert s1.est_tokens == s1.char_count // 4

    s2 = sources_manager.add_source(
        title="Sample Note B",
        content="Secondary research paper observations on attention mechanisms.",
        source_type="upload",
        filename="paper.txt",
        sources_file=test_file,
    )

    loaded = sources_manager.load_sources(sources_file=test_file)
    assert len(loaded) == 2, f"Expected 2 loaded sources, got {len(loaded)}"

    # Test packing with small budget
    budget_small = 60
    pack_small = sources_manager.pack_sources_for_context(loaded, char_budget=budget_small)
    assert pack_small.budget_chars == budget_small
    assert pack_small.budget_tokens == budget_small // 4
    assert len(pack_small.packed_sources) <= 2
    print(f"  [OK] Packed {len(pack_small.packed_sources)} / {len(loaded)} sources into {budget_small} char budget.")

    # Test packing with 512K context budget (e.g. 1,000,000 chars)
    budget_large = 1_000_000
    pack_large = sources_manager.pack_sources_for_context(loaded, char_budget=budget_large)
    assert len(pack_large.packed_sources) == 2
    assert pack_large.packed_tokens == pack_large.packed_chars // 4
    print(f"  [OK] Agnes 512K context packing verified: {pack_large.packed_chars} chars, ~{pack_large.packed_tokens} tokens.")

    # Clean up test file
    if test_file.exists():
        test_file.unlink()


def test_web_search_module():
    print("[3/4] Testing isolated web search module...")
    # Empty query should return empty list gracefully without network call
    res = web_search.search_web("", max_results=2)
    assert isinstance(res, list)
    assert len(res) == 0
    print("  [OK] Isolated web search module handles inputs cleanly.")


def test_streamlit_app_compiles():
    print("[4/4] Testing app.py syntax and module compilation...")
    import py_compile
    py_compile.compile(str(ROOT / "app.py"), doraise=True)
    print("  [OK] app.py compiled successfully with zero syntax errors.")


if __name__ == "__main__":
    try:
        test_client_configuration()
        test_sources_and_context_packing()
        test_web_search_module()
        test_streamlit_app_compiles()
        print("\nALL SMOKE TESTS PASSED.")
        sys.exit(0)
    except Exception as exc:
        print(f"\nSMOKE TEST FAILED: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
