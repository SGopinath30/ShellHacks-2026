"""Compare fixed-width and paragraph-aware parsing on a document.

Run with ``python -m extraction.experiments.compare_chunking FILE --utility-id ID``.
The output is JSON so experiment runs can be checked into an artifact store.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

from extraction.parsing import parse_document


def compare(path: Path, utility_id: str, chunk_size: int) -> dict[str, dict[str, float | int]]:
    results: dict[str, dict[str, float | int]] = {}
    for strategy in ("fixed", "paragraph"):
        started = time.perf_counter()
        chunks = parse_document(
            path,
            utility_id=utility_id,
            chunk_size=chunk_size,
            strategy=strategy,
        )
        elapsed_ms = (time.perf_counter() - started) * 1_000
        sizes = [len(chunk.content) for chunk in chunks]
        results[strategy] = {
            "chunks": len(chunks),
            "characters": sum(sizes),
            "mean_chunk_characters": statistics.fmean(sizes) if sizes else 0,
            "max_chunk_characters": max(sizes, default=0),
            "elapsed_ms": round(elapsed_ms, 3),
        }
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--utility-id", required=True)
    parser.add_argument("--chunk-size", type=int, default=4_000)
    args = parser.parse_args()
    print(json.dumps(compare(args.path, args.utility_id, args.chunk_size), indent=2))


if __name__ == "__main__":
    main()
