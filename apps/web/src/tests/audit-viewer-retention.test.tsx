/**
 * audit-viewer-retention.test.tsx — T209 자료유지 정책 렌더 regression.
 *
 * Verifies the AUDIT_VIEWER E4 retention-policy panel is present, lists all
 * 6 canonical retention categories, and references SEC-02 + 금소법 §28.
 */

import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { AuditViewerPage } from "../pages/AuditViewerPage";

afterEach(cleanup);

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AuditViewerPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AuditViewerPage T209 retention-policy panel", () => {
  it("renders a section with aria-label 자료유지 및 보존 정책", () => {
    renderPage();
    const section = screen.getByRole("region", { name: "자료유지 및 보존 정책" });
    expect(section).toBeInTheDocument();
  });

  it("lists all 6 canonical retention categories", () => {
    renderPage();
    const required = [
      "감사 로그 (audit_logs)",
      "AI 출력 (ai_outputs)",
      "상담 게이트 증빙",
      "이메일 초안 (email_drafts)",
      "자료요구 응답 (info_access)",
      "신용정보 (credit_info)",
    ];
    for (const label of required) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it("calls out 금소법 §28 자료유지·열람권 reference", () => {
    renderPage();
    expect(screen.getByText(/금소법 §28/)).toBeInTheDocument();
  });

  it("links to SEC-02 data privacy doc", () => {
    renderPage();
    const link = screen.getByRole("link", { name: /SEC-02 데이터 프라이버시/ });
    expect(link).toHaveAttribute("href", "/docs/security/SEC-02_data_privacy.md");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("declares AUDIT_VIEWER role read-only (조회·내보내기 권한)", () => {
    renderPage();
    expect(screen.getByText(/AUDIT_VIEWER 역할은 조회·내보내기 권한만 보유합니다/)).toBeInTheDocument();
  });

  it("retention periods include 10년 (audit_logs append-only)", () => {
    renderPage();
    expect(screen.getByText(/10년.*append-only/)).toBeInTheDocument();
  });
});
