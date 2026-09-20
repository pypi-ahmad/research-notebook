"""Smoke test verifying imports, source manager, context packing, and client setup.

Per instructions: No LLM API calls are made in this test.
"""

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from openai import RateLimitError

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import client
import sources_manager
import web_search
from src import ask, brief, config, ingest, ocr_pages, pdf_engine
from src.pack import COLLECTION_NAME


def test_client_configuration():
    print("[1/7] Testing Agnes client configuration...")
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
    assert isinstance(config.agnes_key_is_set(), bool)
    assert callable(client.call_chat_completion_with_retry)

    completions = SimpleNamespace(calls=0)

    def create(**_kwargs):
        completions.calls += 1
        if completions.calls == 1:
            response = httpx.Response(
                429, request=httpx.Request("POST", "https://example.invalid")
            )
            raise RateLimitError("rate limited", response=response, body=None)
        return "retried"

    completions.create = create
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    with patch("src.agnes_client.time.sleep"):
        assert (
            client.call_chat_completion_with_retry(fake_client, max_retries=2)
            == "retried"
        )
    assert completions.calls == 2
    print("  [OK] Agnes AI client instance verified without API call.")


def test_sources_and_context_packing():
    print("[2/7] Testing sources JSONL storage and context packing...")
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

    sources_manager.add_source(
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
    pack_small = sources_manager.pack_sources_for_context(
        loaded, char_budget=budget_small
    )
    assert pack_small.budget_chars == budget_small
    assert pack_small.budget_tokens == budget_small // 4
    assert len(pack_small.packed_sources) <= 2
    print(
        f"  [OK] Packed {len(pack_small.packed_sources)} / {len(loaded)} sources into {budget_small} char budget."
    )

    # Test packing with a large context budget.
    budget_large = 1_000_000
    pack_large = sources_manager.pack_sources_for_context(
        loaded, char_budget=budget_large
    )
    assert len(pack_large.packed_sources) == 2
    assert pack_large.packed_tokens == pack_large.packed_chars // 4
    print(
        f"  [OK] Large-context packing verified: {pack_large.packed_chars} chars, ~{pack_large.packed_tokens} tokens."
    )

    # Clean up test file
    if test_file.exists():
        test_file.unlink()


def test_pdf_routes():
    print("[3/7] Testing pdf-inspector native text and missing-Ollama routes...")
    text_result = SimpleNamespace(
        pdf_type="text_based",
        confidence=0.99,
        page_count=1,
        markdown="# Native text",
        pages_needing_ocr=[],
    )
    scanned_result = SimpleNamespace(
        pdf_type="scanned",
        confidence=0.95,
        page_count=2,
        markdown="Native fragment",
        pages_needing_ocr=[1, 2],
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        with patch.object(pdf_engine, "DEFAULT_PAGES_DIR", Path(temp_dir)):
            with patch.object(
                pdf_engine.pdf_inspector, "process_pdf", return_value=text_result
            ):
                extracted = pdf_engine.process_pdf_document(b"fixture", "text.pdf")
                assert extracted.markdown == "# Native text"
                assert extracted.route == "native"
                assert not extracted.warnings

            with patch.object(
                pdf_engine.pdf_inspector, "process_pdf", return_value=scanned_result
            ):
                with patch.object(
                    pdf_engine,
                    "_ollama_model_available",
                    return_value=(
                        False,
                        "Ollama OCR is unavailable; skipped OCR pages.",
                    ),
                ):
                    extracted = pdf_engine.process_pdf_document(b"fixture", "scan.pdf")
                    assert extracted.markdown == "Native fragment"
                    assert extracted.pages_routed_to_ollama == []
                    assert extracted.route == "ollama"
                    assert extracted.warnings == [
                        "Ollama OCR is unavailable; skipped OCR pages."
                    ]

    native_pdf = pdf_engine.PdfExtractionResult(
        pdf_type="text_based",
        route="native",
        confidence=0.99,
        page_count=1,
        markdown="# Native text",
    )
    with tempfile.TemporaryDirectory() as temp_dir:
        sources_dir = Path(temp_dir)
        with patch.object(ingest, "process_pdf_document", return_value=native_pdf):
            with patch.object(ingest, "index_sources_to_qdrant", return_value=1):
                saved = ingest.ingest_upload(
                    b"fixture", "text.pdf", sources_dir=sources_dir
                )
        assert saved.source.pdf_type == "text_based"
        assert saved.source.route == "native"
        assert ingest.load_sources(sources_dir)[0].route == "native"
    print("  [OK] PDF routing keeps native text and skips unavailable OCR cleanly.")


def test_qdrant_contract():
    print("[4/7] Testing embedded Qdrant collection contract...")
    assert COLLECTION_NAME == "sources"
    print("  [OK] Embedded Qdrant collection is 'sources'.")


def test_scaffold_and_fixtures():
    print("[5/7] Testing src facades and Riverstone fixtures...")
    assert callable(ingest.ingest_text)
    assert callable(ingest.ingest_upload)
    assert callable(ask.ask_question)
    assert callable(brief.generate_brief)
    assert callable(ocr_pages.list_ollama_tags)

    paper_a = (ROOT / "data" / "fixtures" / "paper_a.txt").read_text(encoding="utf-8")
    paper_b = (ROOT / "data" / "fixtures" / "paper_b.txt").read_text(encoding="utf-8")
    assert "Riverstone glass melts at 812 C" in paper_a
    assert "Riverstone glass is mined in Hale County" in paper_b
    assert "812" not in paper_b
    print("  [OK] Requested modules import and fixture facts are isolated.")


def test_web_search_module():
    print("[6/7] Testing isolated web search module with Web OFF behavior...")
    # Empty query should return empty list gracefully without network call
    res = web_search.search_web("", max_results=2)
    assert isinstance(res, list)
    assert len(res) == 0
    print("  [OK] Isolated web search module handles inputs cleanly.")


def test_streamlit_app_compiles():
    print("[7/7] Testing app.py syntax and module compilation...")
    import py_compile

    py_compile.compile(str(ROOT / "app.py"), doraise=True)
    print("  [OK] app.py compiled successfully with zero syntax errors.")


if __name__ == "__main__":
    try:
        test_client_configuration()
        test_sources_and_context_packing()
        test_pdf_routes()
        test_qdrant_contract()
        test_scaffold_and_fixtures()
        test_web_search_module()
        test_streamlit_app_compiles()
        print("\nALL SMOKE TESTS PASSED.")
        sys.exit(0)
    except Exception as exc:
        print(f"\nSMOKE TEST FAILED: {exc}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)
