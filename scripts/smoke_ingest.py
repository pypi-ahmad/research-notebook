"""Offline ingestion smoke. No Agnes API calls."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.ingest import delete_source, get_source_point_counts, ingest_upload
from src.pack import QDRANT_LOCK_MESSAGE

CACHE_PATH = ROOT / "data" / "cache" / "last_ingest.json"


def _remove_previous_smoke_sources() -> None:
    if not CACHE_PATH.exists():
        return
    previous = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    for source_id in previous.get("source_ids", []):
        delete_source(source_id)


def main() -> int:
    """Ingest text fixtures, verify Qdrant points, and write cache metadata.

    Returns:
        Zero on success or two when the embedded Qdrant path is locked.
    """
    try:
        _remove_previous_smoke_sources()
        results = []
        for fixture_name in ("paper_a.txt", "paper_b.txt"):
            fixture = ROOT / "data" / "fixtures" / fixture_name
            results.append(
                ingest_upload(
                    fixture.read_bytes(), fixture_name, title=fixture.stem
                )
            )

        source_ids = [result.source.id for result in results]
        point_counts = get_source_point_counts(source_ids)
        if any(point_counts[source_id] < 1 for source_id in source_ids):
            raise RuntimeError("Each fixture must create at least one Qdrant point.")

        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "source_ids": source_ids,
            "point_counts": point_counts,
        }
        CACHE_PATH.write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )
        print(json.dumps(payload, indent=2))
        return 0
    except RuntimeError as error:
        if QDRANT_LOCK_MESSAGE in str(error):
            print(QDRANT_LOCK_MESSAGE, file=sys.stderr)
            return 2
        raise


if __name__ == "__main__":
    raise SystemExit(main())
