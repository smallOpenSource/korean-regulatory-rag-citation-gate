/**
 * autopilot-demo.test.tsx — T254 자율 시연 시나리오 regression.
 *
 * Verifies the AutopilotDemoPage renders all 6 steps, declares the 30s SLO,
 * shows the simulation warning, and exposes the canonical service refs so
 * audit reviewers can trace each step back to its Stage 3-5 service module.
 */

import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { AutopilotDemoPage } from "../pages/AutopilotDemoPage";

afterEach(cleanup);

function renderPage() {
  return render(
    <MemoryRouter>
      <AutopilotDemoPage />
    </MemoryRouter>,
  );
}

describe("AutopilotDemoPage T254 regression", () => {
  it("renders the page title and 30s SLO copy", () => {
    renderPage();
    // Separator-tolerant regex: page emits "자율 시연 · 1-click 시나리오"
    // (middle-dot); earlier revisions used em-dash. Match the substantive
    // text on both sides so a future copy adjustment does not break the test.
    expect(screen.getByRole("heading", { name: /자율 시연.*1-click 시나리오/ })).toBeInTheDocument();
    expect(screen.getAllByText(/30초/).length).toBeGreaterThan(0);
  });

  it("shows the simulation warning banner", () => {
    renderPage();
    expect(screen.getByText(/시뮬레이션.*실제 주문 아님/)).toBeInTheDocument();
  });

  it("renders all 6 canonical demo steps", () => {
    renderPage();
    expect(screen.getByText(/1\. 합성 고객 선택/)).toBeInTheDocument();
    expect(screen.getByText(/2\. 적합성 자동 평가/)).toBeInTheDocument();
    expect(screen.getByText(/3\. 4-gate 자동 통과/)).toBeInTheDocument();
    expect(screen.getByText(/4\. AI 추천 시뮬레이션/)).toBeInTheDocument();
    expect(screen.getByText(/5\. NBA 인박스 dispatch/)).toBeInTheDocument();
    expect(screen.getByText(/6\. 사후관리 분기 통지 시뮬/)).toBeInTheDocument();
  });

  it("references each Stage 3-5 service module", () => {
    renderPage();
    expect(screen.getByText(/T256 seed_50_family_personas\.sql/)).toBeInTheDocument();
    expect(screen.getByText(/T221 suitability_update_notice\.classify/)).toBeInTheDocument();
    expect(screen.getByText(/T258 four_eyes\.request_approval/)).toBeInTheDocument();
    expect(screen.getByText(/T235 readability\.evaluate_ai_output \+ T205 reasoning_lint/)).toBeInTheDocument();
    expect(screen.getByText(/T246 quarterly_report\.compose_draft/)).toBeInTheDocument();
    expect(screen.getByText(/T257 quarterly_notification/)).toBeInTheDocument();
  });

  it("exposes start + reset controls with aria labels", () => {
    renderPage();
    expect(screen.getByRole("button", { name: "자율 시연 시작" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "초기화" })).toBeInTheDocument();
  });

  it("start button is initially enabled, reset is enabled", () => {
    renderPage();
    expect(screen.getByRole("button", { name: "자율 시연 시작" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "초기화" })).toBeEnabled();
  });

  it("initial state shows all steps as 대기 (pending)", () => {
    renderPage();
    const pendingChips = screen.getAllByText(/^대기$/);
    expect(pendingChips.length).toBe(6);
  });

  it("does not show result summary until the demo runs", () => {
    renderPage();
    expect(screen.queryByText(/시연 결과 요약/)).toBeNull();
  });
});
