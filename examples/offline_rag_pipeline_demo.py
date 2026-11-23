"""Offline demo of the ingestion half of the RAG pipeline (no DB, no network).

Runs the same functions the batch transform stage uses:

1. ``extract_dart_xml_sections``  - OpenDART XML section parsing + injection quarantine
2. ``chunk_text``                 - overlapping word-token chunking
3. ``get_synthetic_vector``       - deterministic 1024-dim fixture vector (pgvector shape)
4. ``vector_literal``             - pgvector text literal used by the embed stage

The fixture vector is NOT a semantic embedding. Real runs call the BGE-m3 endpoint
configured by ``BGE_EMBEDDING_API_URL``.

Usage (from the repository root):
    python examples/offline_rag_pipeline_demo.py
    python examples/offline_rag_pipeline_demo.py --xml path/to/document.xml --chunk-tokens 40
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from apps.api.harness.batch.documents import (  # noqa: E402
    DEFAULT_CHUNK_OVERLAP_TOKENS,
    DEFAULT_CHUNK_TOKENS,
    chunk_text,
    extract_dart_xml_sections,
)
from apps.api.harness.batch.embedding import vector_literal  # noqa: E402
from apps.api.harness.services.rag.embedding_config import (  # noqa: E402
    EXPECTED_DIMENSIONS,
    get_synthetic_vector,
)

DEFAULT_XML = REPO_ROOT / "examples" / "sample_data" / "dart_sample_document.xml"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--xml", type=Path, default=DEFAULT_XML)
    parser.add_argument("--chunk-tokens", type=int, default=DEFAULT_CHUNK_TOKENS)
    parser.add_argument("--overlap-tokens", type=int, default=DEFAULT_CHUNK_OVERLAP_TOKENS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    raw_xml = args.xml.read_text(encoding="utf-8")
    sections = extract_dart_xml_sections(raw_xml)
    quarantined = sum(section.quarantined_lines for section in sections)
    print(f"source: {args.xml.name}")
    print(f"sections: {len(sections)}  quarantined_lines: {quarantined}")

    chunk_count = 0
    for section_no, section in enumerate(sections, start=1):
        chunks = chunk_text(
            section.text,
            chunk_tokens=args.chunk_tokens,
            overlap_tokens=args.overlap_tokens,
        )
        print(f"\n[{section_no}] {section.path}  (quarantined={section.quarantined_lines})")
        for chunk_no, chunk in enumerate(chunks, start=1):
            chunk_count += 1
            chunk_key = f"{args.xml.name}#{section_no}.{chunk_no}"
            vector = get_synthetic_vector(chunk_key)
            literal = vector_literal(vector)
            print(f"  chunk {chunk_no}: tokens={chunk.token_count} text={chunk.text[:60]}...")
            print(f"    vector dims={len(vector)} literal_prefix={literal[:40]}...")
            if len(vector) != EXPECTED_DIMENSIONS:
                print("    DIMENSION_MISMATCH", file=sys.stderr)
                return 1

    print(f"\ntotal chunks: {chunk_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
