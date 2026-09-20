"""Optional PDF smoke; absence of the fixture is an expected skip."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.pdf_engine import process_pdf_document

FIXTURE = ROOT / "data" / "fixtures" / "text.pdf"
CACHE_PATH = ROOT / "data" / "cache" / "pdf_optional.json"


def main() -> int:
    """Inspect an optional PDF fixture and always record a cache result.

    Returns:
        Zero whether the fixture is processed or absent and therefore skipped.
    """
    if not FIXTURE.exists():
        record = {
            "status": "skipped",
            "reason": "data/fixtures/text.pdf does not exist",
        }
    else:
        result = process_pdf_document(FIXTURE.read_bytes(), FIXTURE.name)
        record = {
            "status": "passed",
            "pdf_type": result.pdf_type,
            "route": result.route,
            "page_count": result.page_count,
            "markdown_chars": len(result.markdown),
            "warnings": result.warnings,
        }

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
