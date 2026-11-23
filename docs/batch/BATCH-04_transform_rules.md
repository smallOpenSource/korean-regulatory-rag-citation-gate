# BATCH-04 Transform Rules

## Text Documents
- raw_documents.raw_text → HTML/PDF 파싱 → 순수 텍스트 추출.
- 텍스트 정규화: 공백 통일, 특수문자 처리.
- documents 테이블에 메타데이터 저장.
- raw_documents.is_processed=true, processed_at=now() 업데이트.

## Chunking
- 청크 크기: 512 tokens (tiktoken 계산).
- 오버랩: 64 tokens.
- 청크 저장: document_chunks (chunk_no, chunk_text, is_embedded=false).

## Rules
- 이미 processed인 raw_documents 재처리 금지.
- 빈 청크 (chunk_text len < 50) 저장 제외.

## Implemented Transform Contract
- `apps/api/harness/batch/documents.py` reads only `raw_documents.is_processed=false` rows,
  normalizes whitespace, creates deterministic `documents` rows, inserts overlapping
  `document_chunks`, and marks the raw row processed after chunk handling.
- The current implementation uses a dependency-free word-token approximation for the documented
  512/64 chunk/overlap defaults because no tokenizer dependency has been approved.
- Empty or too-short raw text is marked processed and counted as skipped so the transform queue does
  not retry forever.
- Generated document titles use source type plus content hash prefix, not provider URL query strings,
  to avoid leaking service keys or customer data into titles/logs.

## Seeded MANUAL Baseline
- The full-MVP seed includes two MANUAL baseline raw documents plus normalized documents/chunks.
- These rows are internal synthetic guidance only and do not represent DART/REG_PAGE/RESEARCH/WEB_SEARCH provider data.
- Provider-labelled raw documents must be collected through real provider jobs with URL/hash lineage.
