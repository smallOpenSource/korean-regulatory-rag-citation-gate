#!/usr/bin/env python
"""Wave G (G1) — RAGAS faithfulness + answer_relevancy scorer.

Mirrors scripts/wave_g_deepeval.py: same ai_outputs source, same Azure
adapter (.env override), same per-trace JSON + aggregate summary shape.
Different metric stack — RAGAS Faithfulness + AnswerRelevancy via
LangChain Azure wrapper.

Thresholds (ADR-009 §dim-9-extension target):
  - faithfulness >= 0.85
  - answer_relevancy >= 0.80

Per [[adr-spec-sot-verification]]: thresholds bound here, propagated
to ADR-009 only after an actual run produces distributions.

Usage:
  python scripts/wave_g_ragas.py --n 3 --pilot
  python scripts/wave_g_ragas.py --n 30
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 정규 로더를 사용해 HARNESS_ENV_FILE 테스트 오버레이를 존중하고
# assert_critical_env_override stale-OS-env 가드를 거치도록 한다.
from apps.api.harness.core.config import default_env_path, load_env_file  # noqa: E402

load_env_file(default_env_path())

OUT_DIR = PROJECT_ROOT / "audit-out" / "stage-3" / "llm" / "ragas"
SUMMARY_PATH = PROJECT_ROOT / "audit-out" / "stage-3" / "llm" / "ragas-summary.json"

FAITHFULNESS_MIN = 0.85
ANSWER_RELEVANCY_MIN = 0.80


from ragas.embeddings.base import BaseRagasEmbedding


class BGEEmbeddings(BaseRagasEmbedding):
    """RAGAS-compatible embeddings backed by the internal BGE endpoint
    (.env BGE_EMBEDDING_API_URL). The endpoint accepts
    ``{"texts": [...]}`` and returns ``{"dense_embeddings": [[...]]}``,
    so the stock OpenAI-shape embedding_factory cannot wrap it.

    Subclasses the **modern** BaseRagasEmbedding interface that the
    collections.AnswerRelevancy metric validates against.
    """

    def __init__(self, base_url: str, api_key: str | None = None, model: str = "BAAI/bge-m3"):
        import httpx
        self._httpx = httpx
        self._base_url = base_url.rstrip("/")
        self._headers = {"Content-Type": "application/json"}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"
        self.model = model
        # NOTE: ragas .score() drives a fresh asyncio.run() per metric call,
        # which closes the surrounding event loop on exit. A long-lived
        # httpx.AsyncClient created at __init__ would bind to that closed
        # loop and raise "Event loop is closed" on the next call. We
        # instead spin a fresh client per request — slightly more overhead
        # per call (a few ms TCP setup) but immune to the loop lifecycle.

    def _post(self, texts):
        with self._httpx.Client(timeout=300) as client:
            resp = client.post(self._base_url, headers=self._headers, json={"texts": list(texts)})
            resp.raise_for_status()
            return resp.json()["dense_embeddings"]

    async def _apost(self, texts):
        async with self._httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(self._base_url, headers=self._headers, json={"texts": list(texts)})
            resp.raise_for_status()
            return resp.json()["dense_embeddings"]

    def embed_text(self, text):
        return self._post([text])[0]

    def embed_texts(self, texts):
        return self._post(texts)

    async def aembed_text(self, text):
        return (await self._apost([text]))[0]

    async def aembed_texts(self, texts):
        return await self._apost(texts)

    def embed_query(self, text):
        return self.embed_text(text)

    def embed_documents(self, texts):
        return self.embed_texts(texts)

    async def aembed_query(self, text):
        return await self.aembed_text(text)

    async def aembed_documents(self, texts):
        return await self.aembed_texts(texts)


def build_azure_llm_embeddings():
    from openai import AsyncAzureOpenAI
    from ragas.llms import llm_factory

    endpoint = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")
    deployment = os.environ.get("AZURE_GPT5_MINI_DEPLOYMENT") or os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"]
    api_key = os.environ["AZURE_OPENAI_API_KEY"]
    api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")

    azure_client = AsyncAzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version=api_version,
    )

    # gpt-5.5 reasoning model rejects max_tokens and requires
    # max_completion_tokens. Both RAGAS via instructor and many older
    # adapters still emit max_tokens. Intercept create() on this client
    # to translate the kwarg at the boundary.
    original_create = azure_client.chat.completions.create

    # Reasoning-class deployments (gpt-5.x) reject several params that
    # legacy chat callers still emit. Drop them at the boundary so the
    # request reaches the API in a shape it accepts.
    GPT5_UNSUPPORTED = {"temperature", "top_p", "presence_penalty", "frequency_penalty", "logprobs", "top_logprobs"}

    async def patched_create(*args, **kwargs):
        for k in GPT5_UNSUPPORTED:
            kwargs.pop(k, None)
        if "max_tokens" in kwargs and "max_completion_tokens" not in kwargs:
            kwargs["max_completion_tokens"] = kwargs.pop("max_tokens")
        return await original_create(*args, **kwargs)

    azure_client.chat.completions.create = patched_create  # type: ignore[method-assign]

    llm = llm_factory(model=deployment, provider="openai", client=azure_client)

    # AnswerRelevancy embeddings come from the internal BGE service
    # (.env EMBEDDING_PROVIDER=internal_bge / BGE_EMBEDDING_API_URL).
    # The BGE endpoint shape (texts→dense_embeddings) is not OpenAI-
    # compatible, so we wrap it in a custom BGEEmbeddings adapter
    # instead of routing through embedding_factory.
    bge_url = os.environ.get("BGE_EMBEDDING_API_URL")
    bge_key = os.environ.get("BGE_EMBEDDING_API_KEY")
    bge_model = os.environ.get("BGE_EMBEDDING_MODEL", "BAAI/bge-m3")
    embeddings_obj = None
    embed_meta = None
    if bge_url:
        try:
            embeddings_obj = BGEEmbeddings(base_url=bge_url, api_key=bge_key, model=bge_model)
            embed_meta = f"{bge_url} (model={bge_model})"
        except Exception as exc:  # noqa: BLE001
            print(f"[wave_g_ragas] BGE embeddings init skipped: {exc}", flush=True)

    return (
        llm,
        embeddings_obj,
        {
            "endpoint": endpoint,
            "chat_deployment": deployment,
            "embed_deployment": embed_meta,
            "api_version": api_version,
        },
    )


def fetch_traces(n: int) -> list[dict]:
    dsn = os.environ["DATABASE_URL"]
    sql = """
        SELECT id, agent_id, resource_type, output_json, citations_json, question_text
        FROM ai_outputs
        WHERE output_json IS NOT NULL
          AND citations_json IS NOT NULL
          AND jsonb_array_length(citations_json) > 0
        ORDER BY question_text IS NULL ASC, created_at DESC
        LIMIT %s
    """
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(sql, (n,))
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in rows]


def extract_question_answer_context(row: dict) -> tuple[str, str, list[str], str]:
    """Returns (user_input, answer, context, question_source).

    question_source: "extracted" if V065-backfilled or write-side
    captured a real user question; "placeholder" if the substitute
    "Q for resource_type=..." had to be used (per residual-v5 ralplan
    Pre-mortem Scenario 1 mitigation).
    """
    out = row["output_json"] or {}
    answer = (out.get("answer") or "").strip()
    citations = row["citations_json"] or []
    chunks = [(c.get("quote") or "").strip() for c in citations if c.get("quote")]

    # 1) Prefer V065 question_text column (post-2026-05-23 amend).
    question_text = (row.get("question_text") or "").strip() if row.get("question_text") else ""
    if question_text:
        return question_text, answer, [c for c in chunks if c], "extracted"

    # 2) Legacy output_json->>'question' (rare).
    legacy_question = (out.get("question") or "").strip()
    if legacy_question:
        return legacy_question, answer, [c for c in chunks if c], "extracted"

    # 3) Synthetic placeholder — caller treats this as a per-row floor,
    # not the canonical answer-relevance verdict.
    placeholder = f"Q for resource_type={row.get('resource_type') or 'unknown'}"
    return placeholder, answer, [c for c in chunks if c], "placeholder"


def score_one(llm, embeddings, faith_metric, relevancy_metric, user_input: str, answer: str, context: list[str], trace_id: str) -> dict:
    import asyncio

    record: dict = {
        "trace_id": trace_id,
        "user_input_len": len(user_input),
        "response_len": len(answer),
        "context_chunks": len(context),
    }

    try:
        result_f = faith_metric.score(user_input=user_input, response=answer, retrieved_contexts=context)
        score_f = float(result_f.value if hasattr(result_f, "value") else result_f)
        record["faithfulness_score"] = score_f
        record["faithfulness_pass"] = score_f >= FAITHFULNESS_MIN
    except Exception as exc:  # noqa: BLE001
        record["faithfulness_error"] = f"{type(exc).__name__}: {exc}"

    if embeddings is not None and relevancy_metric is not None:
        try:
            # AnswerRelevancy.score signature in ragas.metrics.collections
            # is (user_input, response) — it does NOT take
            # retrieved_contexts (unlike Faithfulness which does).
            result_r = relevancy_metric.score(user_input=user_input, response=answer)
            score_r = float(result_r.value if hasattr(result_r, "value") else result_r)
            record["answer_relevancy_score"] = score_r
            record["answer_relevancy_pass"] = score_r >= ANSWER_RELEVANCY_MIN
        except Exception as exc:  # noqa: BLE001
            record["answer_relevancy_error"] = f"{type(exc).__name__}: {exc}"
    else:
        record["answer_relevancy_skipped"] = "embeddings_unavailable"

    return record


def aggregate(records: list[dict]) -> dict:
    def mean(key: str) -> float | None:
        vals = [r[key] for r in records if isinstance(r.get(key), (int, float))]
        return round(sum(vals) / len(vals), 4) if vals else None

    return {
        "n_total": len(records),
        "n_faithfulness_scored": sum(1 for r in records if "faithfulness_score" in r),
        "n_answer_relevancy_scored": sum(1 for r in records if "answer_relevancy_score" in r),
        "n_faithfulness_pass": sum(1 for r in records if r.get("faithfulness_pass") is True),
        "n_answer_relevancy_pass": sum(1 for r in records if r.get("answer_relevancy_pass") is True),
        "n_question_source_extracted": sum(1 for r in records if r.get("question_source") == "extracted"),
        "n_question_source_placeholder": sum(1 for r in records if r.get("question_source") == "placeholder"),
        "mean_faithfulness": mean("faithfulness_score"),
        "mean_answer_relevancy": mean("answer_relevancy_score"),
        "threshold_faithfulness_min": FAITHFULNESS_MIN,
        "threshold_answer_relevancy_min": ANSWER_RELEVANCY_MIN,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--pilot", action="store_true")
    # Citation-gate tightening per ADR-009 §G1 per-trace root cause.
    # The current RAG router returns top-5 chunks sorted by similarity.
    # Lowering --top-k drops the lower-similarity tail (the "general
    # guidance" chunks that the NLI judge can't tie any statement to)
    # and is the highest-leverage knob for lifting per-trace pass rate
    # without re-training the extractor.
    ap.add_argument("--top-k", type=int, default=5,
                    help="Truncate retrieved_contexts to top-K chunks (default 5)")
    # C3 measurement flag (ralplan v4 step 3 of 3). Strips the
    # attribution disclaimer + question echo prefix from the answer
    # before passing to RAGAS. Simulates what apps/api/harness/api/
    # routers/ai.py:_build_cited_answer would produce after the C3
    # step 2 refactor (which puts the prefix in output_json
    # .attribution_note instead of bundling it into output_json
    # .answer). Default false to preserve backward-compat for
    # historical comparisons.
    ap.add_argument("--strip-attribution", action="store_true",
                    help="Strip the attribution_note prefix from answer before scoring (C3 measurement mode)")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[wave_g_ragas] building Azure LLM + embeddings...", flush=True)
    from ragas.metrics.collections import Faithfulness, AnswerRelevancy

    llm, embeddings, model_meta = build_azure_llm_embeddings()
    faith_metric = Faithfulness(llm=llm)
    relevancy_metric = None
    if embeddings is not None:
        try:
            relevancy_metric = AnswerRelevancy(llm=llm, embeddings=embeddings)
        except Exception as exc:  # noqa: BLE001
            print(f"[wave_g_ragas] AnswerRelevancy init failed: {exc}", flush=True)

    print(f"[wave_g_ragas] fetching {args.n} traces...", flush=True)
    rows = fetch_traces(args.n)
    print(f"[wave_g_ragas] got {len(rows)} traces", flush=True)

    records: list[dict] = []
    for i, row in enumerate(rows, 1):
        trace_id = str(row["id"])
        user_input, answer, context, question_source = extract_question_answer_context(row)
        # C3 step 3: strip attribution_note prefix to simulate the post-
        # step-2 output_json.answer shape. The prefix pattern matches
        # the hardcoded routers/ai.py line that bundled meta-content
        # with the citation body.
        if args.strip_attribution and answer:
            prefix_marker = "아래 답변은 검색된 승인 청크만 발췌한 근거 기반 요약입니다."
            if prefix_marker in answer:
                # Drop the prefix + question echo, keep only the
                # citation-derived "[1] ... [2] ..." body.
                citation_start = answer.find("[1]")
                if citation_start >= 0:
                    answer = answer[citation_start:].strip()
        if not answer or not context:
            print(f"[{i}/{len(rows)}] {trace_id[:8]} SKIP", flush=True)
            continue
        # Apply citation-gate truncation per --top-k.
        context_gated = context[: args.top_k] if args.top_k > 0 else context
        print(f"[{i}/{len(rows)}] {trace_id[:8]} scoring ({question_source}, top-k={len(context_gated)}/{len(context)})...", flush=True)
        rec = score_one(llm, embeddings, faith_metric, relevancy_metric, user_input, answer, context_gated, trace_id)
        rec["question_source"] = question_source
        rec["context_chunks_retrieved"] = len(context)
        rec["context_chunks_used"] = len(context_gated)
        records.append(rec)
        (OUT_DIR / f"trace-{trace_id}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2))
        f = rec.get("faithfulness_score")
        r = rec.get("answer_relevancy_score")
        print(f"  -> faithfulness={f} answer_relevancy={r}", flush=True)

    summary = aggregate(records)
    summary["pilot"] = bool(args.pilot)
    summary["requested_n"] = args.n
    summary["top_k"] = args.top_k
    summary["strip_attribution"] = bool(args.strip_attribution)
    summary["model"] = model_meta
    summary["generated_at"] = datetime.now(timezone.utc).isoformat()
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Write the canonical summary AND a top-k / strip-tagged copy so
    # multiple runs can be compared without overwriting each other.
    summary_text = json.dumps(summary, ensure_ascii=False, indent=2)
    SUMMARY_PATH.write_text(summary_text)
    tag = f"top{args.top_k}"
    if args.strip_attribution:
        tag += "-strip"
    tagged_path = SUMMARY_PATH.with_name(f"ragas-summary-{tag}.json")
    tagged_path.write_text(summary_text)
    print(f"[wave_g_ragas] summary -> {SUMMARY_PATH} + {tagged_path.name}", flush=True)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
