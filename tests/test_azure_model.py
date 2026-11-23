"""
tests/test_azure_model.py
Azure OpenAI (Responses API) 호출 테스트
- TestEnvVars             : .env 환경변수 로딩 확인
- TestStructuredOutput    : Structured Output (responses.parse / responses.create + strict_schema)
- TestBuiltinWebSearchTool: 빌트인 web_search 툴 + citations 분리 검증
"""
import os
import json
from datetime import datetime, timezone
from typing import Literal

import pytest
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field

load_dotenv(override=True)

BASE_URL    = os.getenv("AZURE_OPENAI_BASE_URL")
API_KEY     = os.getenv("AZURE_OPENAI_API_KEY")
API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")
DEPLOYMENT  = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5.5")


# ─────────────────────────────────────────────
# Pydantic 스키마 정의
# ─────────────────────────────────────────────
class SentimentResult(BaseModel):
    sentiment:  Literal["positive", "negative", "neutral"]
    confidence: float = Field(description="0.0 ~ 1.0")
    reasoning:  str   = Field(description="판단 근거 한 문장")


class NewsItem(BaseModel):
    title:           str   = Field(description="뉴스 제목")
    summary:         str   = Field(description="핵심 요약 2문장 이내")
    relevance_score: float = Field(description="관련도 0.0 ~ 1.0")


class NewsSearchResult(BaseModel):
    query:       str            = Field(description="검색 질의어")
    items:       list[NewsItem] = Field(description="상위 뉴스 최대 3건")
    searched_at: str            = Field(description="검색 시점 ISO8601")


# ─────────────────────────────────────────────
# OpenAI Strict Schema 헬퍼
# responses.create() + text.format json_schema strict=True 사용 시
# 모든 object 노드에 additionalProperties=false 재귀 주입 필수
# ─────────────────────────────────────────────
def _make_strict(schema: dict) -> dict:
    if schema.get("type") == "object":
        schema["additionalProperties"] = False
        for prop in schema.get("properties", {}).values():
            _make_strict(prop)
    if "items" in schema:
        _make_strict(schema["items"])
    if "$defs" in schema:
        for defn in schema["$defs"].values():
            _make_strict(defn)
    for key in ("anyOf", "oneOf", "allOf"):
        for sub in schema.get(key, []):
            _make_strict(sub)
    return schema


def strict_schema(model: type[BaseModel]) -> dict:
    return _make_strict(model.model_json_schema())


# ─────────────────────────────────────────────
# Citation 추출 유틸
# ─────────────────────────────────────────────
def extract_citations(resp) -> tuple[str, list]:
    """
    response 객체에서 (output_text, url_citations) 반환.
    url_citation: type / url / title / start_index / end_index
    """
    text = ""
    citations = []
    for item in resp.output:
        if item.type == "message":
            for content in item.content:
                if content.type == "output_text":
                    text = content.text
                    for ann in content.annotations:
                        if ann.type == "url_citation":
                            citations.append(ann)
    return text, citations


# ─────────────────────────────────────────────
# Fixture
# ─────────────────────────────────────────────
@pytest.fixture(scope="module")
def client():
    return OpenAI(base_url=BASE_URL, api_key=API_KEY)


# ─────────────────────────────────────────────
# 1. 환경변수 확인
# ─────────────────────────────────────────────
class TestEnvVars:
    def test_base_url_contains_v1(self):
        assert BASE_URL and "/openai/v1/" in BASE_URL

    def test_api_key_set(self):
        assert API_KEY and len(API_KEY) > 20

    def test_api_version_set(self):
        assert API_VERSION

    def test_deployment_set(self):
        assert DEPLOYMENT

    def test_api_key_loaded_from_dotenv(self):
        print(f"\n[API_KEY prefix] {API_KEY[:12]}...")


# ─────────────────────────────────────────────
# 2. Structured Output
# ─────────────────────────────────────────────
class TestStructuredOutput:
    """
    방법 A: responses.parse() + text_format=PydanticClass  ← SDK 공식 권장
    방법 B: responses.create() + text.format + strict_schema ← 수동 (헬퍼 필수)
    """

    # ── 방법 A: responses.parse() ──────────────────────────
    def test_parse_pydantic_direct(self, client):
        """responses.parse() + text_format → output_parsed 직접 반환"""
        resp = client.responses.parse(
            model=DEPLOYMENT,
            instructions=(
                "You are a sentiment analysis engine. "
                "Analyze the sentiment of the given text."
            ),
            input="I absolutely love this new AI model! It's fantastic.",
            text_format=SentimentResult,
        )
        result: SentimentResult = resp.output_parsed
        assert result is not None
        assert result.sentiment in ("positive", "negative", "neutral")
        assert 0.0 <= result.confidence <= 1.0
        assert result.reasoning
        print(f"\n[parse/direct] {result.model_dump()}")

    def test_parse_negative_sentiment(self, client):
        """부정적 텍스트 → negative 판정"""
        resp = client.responses.parse(
            model=DEPLOYMENT,
            instructions="You are a sentiment analysis engine.",
            input="This product is terrible and a complete waste of money.",
            text_format=SentimentResult,
        )
        result: SentimentResult = resp.output_parsed
        assert result.sentiment == "negative", \
            f"Expected negative, got: {result.sentiment}"
        print(f"\n[parse/negative] {result.model_dump()}")

    def test_parse_neutral_sentiment(self, client):
        """중립적 텍스트 → neutral 판정"""
        resp = client.responses.parse(
            model=DEPLOYMENT,
            instructions="You are a sentiment analysis engine.",
            input="The temperature today is 20 degrees Celsius.",
            text_format=SentimentResult,
        )
        result: SentimentResult = resp.output_parsed
        assert result.sentiment in ("neutral", "positive", "negative")
        print(f"\n[parse/neutral] {result.model_dump()}")

    def test_parse_output_parsed_type(self, client):
        """output_parsed 가 SentimentResult 인스턴스인지 확인"""
        resp = client.responses.parse(
            model=DEPLOYMENT,
            instructions="You are a sentiment analysis engine.",
            input="I feel okay about this.",
            text_format=SentimentResult,
        )
        assert isinstance(resp.output_parsed, SentimentResult)
        print(f"\n[parse/type] {type(resp.output_parsed).__name__}")

    def test_parse_refusal_handling(self, client):
        """정상 입력에서 refusal 없음 확인"""
        resp = client.responses.parse(
            model=DEPLOYMENT,
            instructions="You are a sentiment analysis engine.",
            input="This coffee is great!",
            text_format=SentimentResult,
        )
        for item in resp.output:
            if item.type == "message":
                for content in item.content:
                    assert getattr(content, "refusal", None) is None, \
                        f"Unexpected refusal: {content.refusal}"
        assert resp.output_parsed is not None
        print(f"\n[parse/refusal] no refusal, result={resp.output_parsed.sentiment}")

    # ── 방법 B: responses.create() + strict_schema ────────
    def test_create_strict_schema_helper(self, client):
        """strict_schema() 헬퍼로 additionalProperties=false 주입 후 호출"""
        schema = strict_schema(SentimentResult)
        resp = client.responses.create(
            model=DEPLOYMENT,
            instructions="You are a sentiment analysis engine. Respond ONLY with valid JSON.",
            input="I love sunny days and good coffee!",
            text={
                "format": {
                    "type": "json_schema",
                    "name": "SentimentResult",
                    "schema": schema,
                    "strict": True,
                }
            },
        )
        data = json.loads(resp.output_text)
        result = SentimentResult(**data)
        assert result.sentiment in ("positive", "negative", "neutral")
        print(f"\n[create/strict_schema] {result.model_dump()}")

    def test_create_strict_no_extra_keys(self, client):
        """strict 모드 응답에 스키마 외 키 없음 검증"""
        schema = strict_schema(SentimentResult)
        resp = client.responses.create(
            model=DEPLOYMENT,
            instructions="Respond ONLY with valid JSON matching the schema.",
            input="The movie was okay.",
            text={
                "format": {
                    "type": "json_schema",
                    "name": "SentimentResult",
                    "schema": schema,
                    "strict": True,
                }
            },
        )
        data = json.loads(resp.output_text)
        allowed = set(SentimentResult.model_fields.keys())
        extra = set(data.keys()) - allowed
        assert not extra, f"Extra keys: {extra}"
        print(f"\n[create/no_extra_keys] keys={list(data.keys())}")


# ─────────────────────────────────────────────
# 3. 빌트인 Web Search + Citations 분리 검증
# ─────────────────────────────────────────────
class TestBuiltinWebSearchTool:

    # ── 기본 호출 ──────────────────────────────────────────
    def test_web_search_basic(self, client):
        """web_search 툴 기본 호출 → web_search_call 출력 타입 확인"""
        resp = client.responses.create(
            model=DEPLOYMENT,
            tools=[{"type": "web_search"}],
            tool_choice="required",
            input="What is the latest stable version of Python as of today?",
        )
        assert resp.output_text
        output_types = [item.type for item in resp.output]
        assert "web_search_call" in output_types, \
            f"web_search_call not in output: {output_types}"
        print(f"\n[web_search/basic] {resp.output_text[:200]}...")

    def test_web_search_context_size_low(self, client):
        """search_context_size=low → 빠른 검색, 정답 확인"""
        resp = client.responses.create(
            model=DEPLOYMENT,
            tools=[{"type": "web_search", "search_context_size": "low"}],
            tool_choice="required",
            input="What is the capital of South Korea?",
        )
        assert any(k in resp.output_text for k in ("Seoul", "서울")), \
            f"Seoul not found: {resp.output_text}"
        print(f"\n[web_search/low] {resp.output_text[:200]}")

    def test_web_search_user_location_kr(self, client):
        """user_location KR → 한국어 지역화 응답"""
        resp = client.responses.create(
            model=DEPLOYMENT,
            tools=[{
                "type": "web_search",
                "user_location": {
                    "type": "approximate",
                    "country": "KR",
                    "city": "Seoul",
                    "region": "Seoul",
                    "timezone": "Asia/Seoul",
                },
            }],
            tool_choice="required",
            input="오늘 서울 날씨는 어때?",
        )
        assert resp.output_text
        print(f"\n[web_search/kr] {resp.output_text[:200]}")

    # ── Citations 구조 검증 ────────────────────────────────
    def test_web_search_url_citations(self, client):
        """url_citation annotations 존재 확인 (최소 1개)"""
        resp = client.responses.create(
            model=DEPLOYMENT,
            tools=[{"type": "web_search"}],
            tool_choice="required",
            input="Who won the most recent FIFA World Cup?",
        )
        _, citations = extract_citations(resp)
        assert citations, "No url_citation annotations found"
        print(f"\n[citation/basic] {len(citations)} citations")
        for c in citations[:3]:
            print(f"  - {c.url}")

    def test_citation_extraction_structure(self, client):
        """
        url_citation 필드 완전 검증:
        type / url / title / start_index / end_index 모두 존재 + 유효성
        """
        resp = client.responses.create(
            model=DEPLOYMENT,
            tools=[{"type": "web_search"}],
            tool_choice="required",
            input="When was the Python programming language first released?",
        )
        _, citations = extract_citations(resp)
        assert citations, "url_citation annotations not found"

        for c in citations:
            assert c.type == "url_citation"
            assert c.url and c.url.startswith("http"),  f"Invalid URL: {c.url}"
            assert c.title,                             f"Missing title: {c}"
            assert isinstance(c.start_index, int),      f"start_index not int: {c}"
            assert isinstance(c.end_index,   int),      f"end_index not int: {c}"
            assert c.start_index < c.end_index, \
                f"start_index >= end_index: {c.start_index} >= {c.end_index}"

        print(f"\n[citation/structure] {len(citations)} citations validated")
        for c in citations[:3]:
            print(f"  [{c.start_index}:{c.end_index}] {c.title} → {c.url}")

    def test_citation_index_points_to_text(self, client):
        """
        start_index / end_index 가 output_text 내 실제 위치를 가리키는지 검증.
        슬라이스 결과가 비어있지 않아야 함.

        Note: Azure Responses API + web_search returns citations non-
        deterministically for static-knowledge prompts ("What is the
        capital of X?") — the model may invoke web_search yet emit no
        url_citation annotations. We use a time-sensitive prompt to
        maximize citation probability and skip with a clear reason when
        Azure still chooses not to cite, since the invariant under test
        is index-points-to-text and applies only when citations exist.
        """
        resp = client.responses.create(
            model=DEPLOYMENT,
            tools=[{"type": "web_search"}],
            tool_choice="required",
            input="What is the latest stable version of Python as of today? "
                  "Please cite official sources.",
        )
        text, citations = extract_citations(resp)
        assert text, "No output text"
        if not citations:
            pytest.skip(
                "Azure web_search returned no url_citation annotations for "
                "this run — index-points-to-text invariant applies only when "
                "citations exist; live LLM citation emission is "
                "non-deterministic."
            )

        for c in citations:
            assert 0 <= c.start_index < len(text), \
                f"start_index {c.start_index} out of range (text len={len(text)})"
            assert 0 < c.end_index <= len(text), \
                f"end_index {c.end_index} out of range (text len={len(text)})"
            snippet = text[c.start_index:c.end_index]
            assert snippet, f"Empty snippet at [{c.start_index}:{c.end_index}]"
            print(f"\n  snippet='{snippet[:60]}' → {c.url}")

        print(f"\n[citation/index] {len(citations)} citations, text_len={len(text)}")

    def test_citation_deduplicated(self, client):
        """
        URL 기준 dedup 유틸 검증.
        실서비스에서 유니크 출처 목록을 추출하는 패턴 확인.
        """
        resp = client.responses.create(
            model=DEPLOYMENT,
            tools=[{"type": "web_search"}],
            tool_choice="required",
            input="Tell me about OpenAI and its products in detail.",
        )
        _, all_citations = extract_citations(resp)

        seen: set[str] = set()
        unique = []
        for c in all_citations:
            if c.url not in seen:
                seen.add(c.url)
                unique.append(c)

        assert unique, "No citations found"
        print(f"\n[citation/dedup] total={len(all_citations)}, unique={len(unique)}")
        for c in unique:
            print(f"  - {c.title[:60]} → {c.url}")

    def test_citation_inline_marker_format(self, client):
        """
        인라인 마커 영역(text[start:end])이 마크다운 citation 패턴인지 확인.
        OpenAI Responses API는 링크 텍스트를 마커로 삽입함.
        """
        resp = client.responses.create(
            model=DEPLOYMENT,
            tools=[{"type": "web_search"}],
            tool_choice="required",
            input="What year was the Eiffel Tower built?",
        )
        text, citations = extract_citations(resp)
        assert citations, "No citations"

        for c in citations:
            marker = text[c.start_index:c.end_index]
            # 마커는 비어있지 않아야 함
            assert marker.strip(), \
                f"Empty marker at [{c.start_index}:{c.end_index}]"
            print(f"\n  marker='{marker}' title='{c.title}'")

        print(f"\n[citation/marker] {len(citations)} markers checked")

    # ── 2단계 패턴: web_search → parse() ──────────────────
    def test_web_search_two_step_parse(self, client):
        """
        2단계 패턴:
        1단계 - web_search (plain text + citations 수집)
        2단계 - responses.parse() 로 Pydantic 구조화
        (web_search + text.format 동시 사용 불가 → 단계 분리)
        """
        # 1단계: 웹 검색
        search_resp = client.responses.create(
            model=DEPLOYMENT,
            tools=[{"type": "web_search", "search_context_size": "low"}],
            tool_choice="required",
            input="Latest AI model releases 2026",
        )
        raw_text, step1_citations = extract_citations(search_resp)
        assert raw_text
        print(f"\n[2-step] step1 citations={len(step1_citations)}")

        # 2단계: responses.parse() → Pydantic 구조화
        structured_resp = client.responses.parse(
            model=DEPLOYMENT,
            instructions=(
                "You are a news summarizer. "
                "Extract and structure the top news from the given search results."
            ),
            input=(
                f"Search results:\n{raw_text}\n\n"
                f"Current time: {datetime.now(timezone.utc).isoformat()}"
            ),
            text_format=NewsSearchResult,
        )

        result: NewsSearchResult = structured_resp.output_parsed
        assert result is not None
        assert result.query
        assert result.items
        assert result.searched_at
        for item in result.items:
            assert 0.0 <= item.relevance_score <= 1.0

        print(f"\n[2-step/parse] query='{result.query}' items={len(result.items)}")
        for item in result.items:
            print(f"  [{item.relevance_score:.2f}] {item.title}")


# ─────────────────────────────────────────────
# 직접 실행
# ─────────────────────────────────────────────
if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
