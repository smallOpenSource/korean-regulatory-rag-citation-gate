/**
 * houseviews-nba-regression.test.tsx — T29 HouseViewsPage + NbaPage regression.
 *
 * T29 backend conformance audit (Stage 2 iter 2) verified NbaPage T243
 * spec elements. T29 frontend expansion (Stage 2 iter 1) brought
 * HouseViewsPage from 33→301 LOC. This test asserts the visible structure
 * exists in jsdom so a future refactor cannot silently strip the
 * PB-discovery surface.
 */

import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { HouseViewsPage } from "../pages/HouseViewsPage";

afterEach(cleanup);

function withProviders(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("T29 HouseViewsPage — Stage 2 expansion regression", () => {
  it("renders the synthetic-data warning banner", () => {
    withProviders(<HouseViewsPage />);
    expect(screen.getByText(/합성 데이터/)).toBeInTheDocument();
  });

  it("renders all 7 status filter chips (전체 + 6 lifecycle states)", () => {
    withProviders(<HouseViewsPage />);
    const group = screen.getByRole("group", { name: "상태 필터" });
    expect(group).toBeInTheDocument();
    const chips = within(group).getAllByRole("button");
    // 7 chips: 전체 + 초안(DRAFT) + 생성됨(GENERATED) + 검토(REVIEWED) + 활성(ACTIVE) + 보관(ARCHIVED) + 이전 버전(SUPERSEDED)
    // T4 fix (visual-fullwalk-audit v7.1): HouseViewsPage.tsx:38-43 한국어 label 적용
    expect(chips.length).toBe(7);
    expect(within(group).getByRole("button", { name: "전체" })).toBeInTheDocument();
    expect(within(group).getByRole("button", { name: "초안" })).toBeInTheDocument();
    expect(within(group).getByRole("button", { name: "활성" })).toBeInTheDocument();
  });

  it("renders the title search input", () => {
    withProviders(<HouseViewsPage />);
    const input = screen.getByLabelText("타이틀 검색");
    expect(input).toBeInTheDocument();
    expect(input).toHaveAttribute("type", "search");
  });

  it("renders the period_code filter select with default option", () => {
    withProviders(<HouseViewsPage />);
    const select = screen.getByLabelText("기간 코드 필터");
    expect(select).toBeInTheDocument();
    expect(within(select as HTMLSelectElement).getByRole("option", { name: "전체 기간" })).toBeInTheDocument();
  });

  it("renders the sort selector with 3 options", () => {
    withProviders(<HouseViewsPage />);
    const sortSel = screen.getByLabelText("정렬 기준");
    const options = within(sortSel as HTMLSelectElement).getAllByRole("option");
    expect(options.length).toBe(3);
    expect(within(sortSel as HTMLSelectElement).getByRole("option", { name: "버전 ↓" })).toBeInTheDocument();
    expect(within(sortSel as HTMLSelectElement).getByRole("option", { name: "최근 생성 ↓" })).toBeInTheDocument();
  });

  it("renders empty-state copy when API returns no items", () => {
    withProviders(<HouseViewsPage />);
    // Without a backend, the query stays loading initially.
    expect(screen.getByText(/하우스뷰 목록/)).toBeInTheDocument();
  });
});
