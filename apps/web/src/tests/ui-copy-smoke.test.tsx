import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusBadge } from "../components/Badges";
import {
  jobTypeLabel,
  readinessCheckLabel,
  sourceLabel,
  statusLabel,
} from "../lib/labels";

describe("UI copy smoke", () => {
  it("maps production-readiness and provider codes to Korean copy", () => {
    expect(statusLabel("SYNTHETIC_ONLY")).toBe("합성 데이터");
    expect(statusLabel("FRESH")).toBe("신선");
    expect(statusLabel("UNVERIFIED")).toBe("검증 전");
    expect(sourceLabel("DATA_GO_KR")).toBe("공공데이터포털");
    expect(sourceLabel("BROKER")).toBe("증권사 Open API");
    expect(sourceLabel("KRX")).toBe("KRX 공식 OpenAPI");
    expect(sourceLabel("PYKRX")).toBe("pykrx 비공식 보조 소스");
    expect(sourceLabel("PYKRX_AUXILIARY_APPROVED")).toBe("pykrx 비공식 보조 소스");
    expect(sourceLabel("OFFICIAL_KRX_APPROVED")).toBe("KRX 공식 정책 승인");
    expect(statusLabel("PYKRX_AUXILIARY_APPROVED")).toBe("pykrx 보조 정책 승인");
    expect(jobTypeLabel("PROVIDER_BROKER")).toBe("증권사 API 수집");
    expect(jobTypeLabel("PROVIDER_KRX")).toBe("KRX 공식/pykrx 수집");
    expect(readinessCheckLabel("provider.krx_policy")).toBe("KRX 공식/PYKRX 출처 정책");
    expect(readinessCheckLabel("market.top200_universe")).toBe("시가총액 상위 200개 기업");
    expect(readinessCheckLabel("market.top200_30d_coverage")).toBe("상위 200개 30일 커버리지");
    expect(readinessCheckLabel("provider.opendart_30d_lineage")).toBe("OpenDART 30일 공시 근거");
    expect(readinessCheckLabel("provider.ecos_macro_window")).toBe("ECOS 거시지표 구간");
    expect(readinessCheckLabel("rag.dart_embedding_readiness")).toBe("OpenDART RAG 임베딩");
    expect(readinessCheckLabel("market.freshness")).toBe("시장 데이터 신선도");
    expect(readinessCheckLabel("provider.strictness")).toBe("공급자 엄격 모드");
  });

  it("renders blocked/degraded Korean status badges without raw business codes", () => {
    render(
      <div>
        <StatusBadge statusCode="SYNTHETIC_ONLY" />
        <StatusBadge statusCode="MISSING" />
        <StatusBadge statusCode="UNVERIFIED" />
        <StatusBadge statusCode="DEGRADED" />
      </div>,
    );

    expect(screen.getByText("합성 데이터")).toBeInTheDocument();
    // Wave-Audit-Defect-Fix D-S2: MISSING used to render the banned "미확인"
    // placeholder; STATUS_LABELS.MISSING now maps to "상태 미확정" per the
    // PB-perspective ban.
    expect(screen.getByText("상태 미확정")).toBeInTheDocument();
    expect(screen.getByText("검증 전")).toBeInTheDocument();
    expect(screen.getByText("주의")).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/\b(SYNTHETIC_ONLY|MISSING|UNVERIFIED|DEGRADED)\b/);
  });
});
