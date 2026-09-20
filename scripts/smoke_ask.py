"""Web-off grounded Ask and Brief smoke against the Riverstone fixtures."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.ask import ask_question
from src.brief import REQUIRED_HEADINGS, generate_brief
from src.ingest import load_sources

CACHE_DIR = ROOT / "data" / "cache"


def _citation_sources(result: dict) -> set[str]:
    return {citation["source"] for citation in result["citations"]}


def main() -> int:
    """Verify grounded fixture answers and a structured brief with Web disabled.

    Returns:
        Zero when both fixture claims have verified source citations.
    """
    ingest_cache = json.loads(
        (CACHE_DIR / "last_ingest.json").read_text(encoding="utf-8")
    )
    expected_ids = ingest_cache["source_ids"]
    by_id = {source.id: source for source in load_sources()}
    sources = [by_id[source_id] for source_id in expected_ids]
    source_a = next(source for source in sources if "812 C" in source.text)
    source_b = next(source for source in sources if "Hale County" in source.text)

    temperature = ask_question(
        "At what temperature does Riverstone glass melt?",
        sources=sources,
        web_enabled=False,
    )
    if "812" not in temperature["answer"]:
        raise AssertionError("Temperature answer does not contain 812.")
    if "Hale County" in temperature["answer"]:
        raise AssertionError("Temperature answer incorrectly uses Hale County.")
    if source_a.id not in _citation_sources(temperature):
        raise AssertionError("Temperature answer does not cite paper_a.")

    mining = ask_question(
        "Where is Riverstone glass mined?",
        sources=sources,
        web_enabled=False,
    )
    if "Hale County" not in mining["answer"]:
        raise AssertionError("Mining answer does not contain Hale County.")
    if source_b.id not in _citation_sources(mining):
        raise AssertionError("Mining answer does not cite paper_b.")

    brief = generate_brief(
        "Riverstone glass facts",
        sources=sources,
        web_enabled=False,
        output_dir=ROOT / "data" / "briefs",
    )
    if not all(heading in brief["content"] for heading in REQUIRED_HEADINGS):
        raise AssertionError("Brief headings are incomplete.")

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_record = {
        "web_enabled": False,
        "answers": [
            {
                "query": temperature["query"],
                "answer": temperature["answer"],
                "citations": temperature["citations"],
                "packed_citations": temperature["packed_citations"],
            },
            {
                "query": mining["query"],
                "answer": mining["answer"],
                "citations": mining["citations"],
                "packed_citations": mining["packed_citations"],
            },
        ],
    }
    (CACHE_DIR / "last_ask.json").write_text(
        json.dumps(cache_record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(cache_record, ensure_ascii=False, indent=2))
    print(f"Brief: {brief['file_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
