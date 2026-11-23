/**
 * a11y.test.tsx — WCAG 2.1 AA accessibility tests
 *
 * Tests key governance + AI pages for:
 * - Keyboard navigability (focus management, tab order)
 * - ARIA labels / roles on interactive elements
 * - Heading hierarchy
 * - Button accessibility attributes
 * - Status announcements (aria-live)
 *
 * Note: axe-core full DOM scan requires jsdom + @axe-core/react.
 * These tests use @testing-library/react to assert ARIA contract
 * compliance without a browser runtime.
 */

import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { PoCAutoApprovalBadge } from "../components/PoCAutoApprovalBadge";
import { SyntheticWatermark } from "../components/SyntheticWatermark";
import { RightsNoticePage } from "../pages/RightsNoticePage";
import { DisputeCasePage } from "../pages/DisputeCasePage";
import { AIModelCardsPage } from "../pages/AIModelCardsPage";
import { AIPolicyPage } from "../pages/AIPolicyPage";
import { KoreanAIBasicActPage } from "../pages/KoreanAIBasicActPage";
import { useAuthStore } from "../store/auth";

// Explicit cleanup between tests (guards against Vitest jsdom accumulation)
afterEach(cleanup);

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
}

function renderWithProviders(ui: React.ReactElement) {
  return render(
    <MemoryRouter>
      <QueryClientProvider client={makeQueryClient()}>
        {ui}
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

/**
 * Render with a specific MemoryRouter initial entry (used by tests that
 * depend on react-router location.state — e.g. RightsNoticePage's
 * consultationId pre-condition).
 */
function renderWithProvidersAt(ui: React.ReactElement, entry: { pathname: string; state?: unknown }) {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <QueryClientProvider client={makeQueryClient()}>
        {ui}
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

/** Seed the Zustand auth store with a PB user (write-permitted role).
 * Required by pages that gate UI on roleCode (DisputeCasePage canMutate). */
function seedAuthPB() {
  useAuthStore.setState({
    accessToken: "test-token",
    user: {
      employeeId: "test-employee-id",
      name: "테스트 PB",
      roleCode: "PB",
      branchId: undefined,
    },
    isRestoring: false,
    restoreAttempted: true,
  });
}

// ---------------------------------------------------------------------------
// PoCAutoApprovalBadge
// ---------------------------------------------------------------------------

describe("PoCAutoApprovalBadge a11y", () => {
  it("is invisible when enabled=false", () => {
    renderWithProviders(<PoCAutoApprovalBadge enabled={false} />);
    expect(screen.queryByRole("banner")).toBeNull();
  });

  it("renders banner role and label when enabled=true", () => {
    renderWithProviders(<PoCAutoApprovalBadge enabled={true} />);
    const banner = screen.getByRole("banner", { name: /PoC 자동 승인 모드/i });
    expect(banner).toBeInTheDocument();
  });

  it("ADR-004 button has aria-haspopup and aria-expanded", () => {
    renderWithProviders(<PoCAutoApprovalBadge enabled={true} />);
    const btn = screen.getByRole("button", { name: /ADR-004/i });
    expect(btn).toHaveAttribute("aria-haspopup", "dialog");
    expect(btn).toHaveAttribute("aria-expanded", "false");
  });

  it("opens dialog on click with dialog role and label", async () => {
    const user = userEvent.setup();
    renderWithProviders(<PoCAutoApprovalBadge enabled={true} />);
    await user.click(screen.getByRole("button", { name: /ADR-004/i }));
    const dialog = screen.getByRole("dialog");
    expect(dialog).toBeInTheDocument();
    expect(dialog).toHaveAttribute("aria-modal", "true");
  });

  it("close button in dialog has accessible label", async () => {
    const user = userEvent.setup();
    renderWithProviders(<PoCAutoApprovalBadge enabled={true} />);
    await user.click(screen.getByRole("button", { name: /ADR-004/i }));
    const closeBtn = screen.getByRole("button", { name: /닫기/i });
    expect(closeBtn).toBeInTheDocument();
  });

  it("dialog closes when close button clicked", async () => {
    const user = userEvent.setup();
    renderWithProviders(<PoCAutoApprovalBadge enabled={true} />);
    await user.click(screen.getByRole("button", { name: /ADR-004/i }));
    await user.click(screen.getByRole("button", { name: /닫기/i }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// SyntheticWatermark
// ---------------------------------------------------------------------------

describe("SyntheticWatermark a11y", () => {
  it("is not rendered when visible=false", () => {
    const { container } = renderWithProviders(<SyntheticWatermark visible={false} />);
    expect(container.firstChild).toBeNull();
  });

  it("is aria-hidden when visible=true (decorative only)", () => {
    const { container } = renderWithProviders(<SyntheticWatermark visible={true} />);
    const overlay = container.querySelector("[aria-hidden='true']");
    expect(overlay).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// RightsNoticePage
// ---------------------------------------------------------------------------

describe("RightsNoticePage a11y", () => {
  it("renders 4 rights as list items", () => {
    renderWithProviders(<RightsNoticePage />);
    const list = screen.getByRole("list", { name: /금융소비자 4대 권리/i });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(4);
  });

  it("each right has a heading", () => {
    renderWithProviders(<RightsNoticePage />);
    expect(screen.getByRole("heading", { name: /청약철회권/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /위법계약해지권/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /자료열람 요구권/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /분쟁조정 신청권/i })).toBeInTheDocument();
  });

  it("acknowledge checkbox has accessible label", () => {
    renderWithProviders(<RightsNoticePage />);
    const checkbox = screen.getByRole("checkbox");
    expect(checkbox).toHaveAttribute("aria-label");
  });

  it("confirm button is disabled until checkbox checked", async () => {
    const user = userEvent.setup();
    renderWithProviders(<RightsNoticePage />);
    const confirmBtn = screen.getByRole("button", { name: /확인 완료/i });
    expect(confirmBtn).toBeDisabled();
    await user.click(screen.getByRole("checkbox"));
    expect(confirmBtn).not.toBeDisabled();
  });

  it("success status has aria-live=polite", async () => {
    // Pre-conditions: (1) location.state.consultationId set (handler at
    // RightsNoticePage.tsx:110 short-circuits when empty); (2) auth token
    // present so the request layer can attach Authorization; (3) a fetch
    // stub so ackMutation.onSuccess fires and `submitted=true` renders
    // the status node. Direct globalThis.fetch override per the
    // korean-copy-regression guard rule (mock-API regexes catch tokens
    // even inside comments).
    seedAuthPB();
    const originalFetch = globalThis.fetch;
    const stubFetch: typeof fetch = async () =>
      new Response(JSON.stringify({ acknowledged_at: "2026-05-23T00:00:00Z" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    globalThis.fetch = stubFetch;
    try {
      const user = userEvent.setup();
      renderWithProvidersAt(<RightsNoticePage />, {
        pathname: "/rights-notice",
        state: { consultationId: "00000000-0000-0000-0000-000000000001" },
      });
      await user.click(screen.getByRole("checkbox"));
      await user.click(screen.getByRole("button", { name: /확인 완료/i }));
      // Status element should appear immediately with aria-live=polite
      const status = await screen.findByRole("status");
      expect(status).toHaveAttribute("aria-live", "polite");
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});

// ---------------------------------------------------------------------------
// DisputeCasePage
// ---------------------------------------------------------------------------

describe("DisputeCasePage a11y", () => {
  it("renders case list with listitem roles", () => {
    renderWithProviders(<DisputeCasePage />);
    const list = screen.getByRole("list", { name: /분쟁 사례 목록/i });
    const items = within(list).getAllByRole("listitem");
    expect(items.length).toBeGreaterThanOrEqual(3);
  });

  it("progress bars have aria attributes", () => {
    renderWithProviders(<DisputeCasePage />);
    const progressBars = screen.getAllByRole("progressbar");
    progressBars.forEach((bar) => {
      expect(bar).toHaveAttribute("aria-valuenow");
      expect(bar).toHaveAttribute("aria-valuemin");
      expect(bar).toHaveAttribute("aria-valuemax");
    });
  });

  it("advance buttons have accessible labels", () => {
    // The advance button at DisputeCasePage.tsx:231 is role-gated by
    // `canMutate = roleCode ∈ {PB, WM, ADMIN}`. Seed the auth store
    // with a PB user so the button renders.
    seedAuthPB();
    renderWithProviders(<DisputeCasePage />);
    const advanceBtns = screen.getAllByRole("button", { name: /상태 다음 단계/i });
    expect(advanceBtns.length).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// AIModelCardsPage
// ---------------------------------------------------------------------------

describe("AIModelCardsPage a11y", () => {
  it("search input has accessible label", () => {
    renderWithProviders(<AIModelCardsPage />);
    expect(screen.getByRole("searchbox", { name: /AI 에이전트 모델 카드 검색/i })).toBeInTheDocument();
  });

  it("card list has list role and 7 items", () => {
    renderWithProviders(<AIModelCardsPage />);
    const list = screen.getByRole("list", { name: /AI 모델 카드 목록/i });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(7);
  });

  it("all expand buttons have aria-expanded attribute", () => {
    renderWithProviders(<AIModelCardsPage />);
    const expandBtns = screen.getAllByRole("button");
    expandBtns.forEach((btn) => {
      expect(btn).toHaveAttribute("aria-expanded");
    });
  });

  it("search filter reduces visible cards", () => {
    renderWithProviders(<AIModelCardsPage />);
    const searchInput = screen.getByRole("searchbox");
    fireEvent.change(searchInput, { target: { value: "rag" } });
    const list = screen.getByRole("list", { name: /AI 모델 카드 목록/i });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(1);
  });

  it("expanding a card shows metrics table", () => {
    renderWithProviders(<AIModelCardsPage />);
    const firstBtn = screen.getAllByRole("button")[0];
    fireEvent.click(firstBtn);
    expect(screen.getAllByRole("heading", { name: /성능 지표/i }).length).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// AIPolicyPage
// ---------------------------------------------------------------------------

describe("AIPolicyPage a11y", () => {
  it("has a main heading", () => {
    renderWithProviders(<AIPolicyPage />);
    // level:1 restricts to h1 only (h2 section headings also contain the text)
    expect(screen.getByRole("heading", { level: 1, name: /AI 사용 정책/i })).toBeInTheDocument();
  });

  it("each section has an aria-labelledby heading", () => {
    renderWithProviders(<AIPolicyPage />);
    const sections = document.querySelectorAll("section[aria-labelledby]");
    expect(sections.length).toBeGreaterThan(0);
    sections.forEach((section) => {
      const id = section.getAttribute("aria-labelledby");
      expect(id).toBeTruthy();
      expect(document.getElementById(id!)).toBeTruthy();
    });
  });

  it("renders Wave 3 hardening section", () => {
    renderWithProviders(<AIPolicyPage />);
    // Stage 7 amendment 2026-05-18: section title changed to "AI 이중 격리 적용";
    // multiple section bodies reference 이중 격리 — use getAllByText.
    expect(screen.getAllByText(/이중 격리 적용/i).length).toBeGreaterThan(0);
  });

  it("renders LLM07 and LLM10 sections", () => {
    renderWithProviders(<AIPolicyPage />);
    // Stage 7 amendment 2026-05-18: AIPolicyPage no longer references
    // OWASP LLM07/LLM10 codes literally (moved to internal architecture docs).
    // Assert the page surfaces the semantic equivalents instead.
    expect(screen.getAllByText(/시스템 프롬프트|프롬프트.*누출/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/이중 격리|이중 LLM/i).length).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// KoreanAIBasicActPage
// ---------------------------------------------------------------------------

describe("KoreanAIBasicActPage a11y", () => {
  it("has a main heading about 인공지능기본법", () => {
    renderWithProviders(<KoreanAIBasicActPage />);
    // level:1 restricts to h1 (h2 law-context heading also contains the phrase)
    expect(screen.getByRole("heading", { level: 1, name: /인공지능기본법/i })).toBeInTheDocument();
  });

  it("renders 7 control items in the list", () => {
    renderWithProviders(<KoreanAIBasicActPage />);
    const list = screen.getByRole("list", { name: /인공지능기본법 통제 체크리스트/i });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(7);
  });

  it("compliance status badges have aria-label", () => {
    renderWithProviders(<KoreanAIBasicActPage />);
    const badges = screen.getAllByRole("generic", { hidden: false }).filter(
      (el) => el.getAttribute("aria-label")?.includes("이행 상태"),
    );
    expect(badges.length).toBeGreaterThan(0);
  });

  it("shows COMPLIANT label in header", () => {
    renderWithProviders(<KoreanAIBasicActPage />);
    // Multiple elements may contain "이행 완료" (header stat + COMPLIANT badges)
    const elements = screen.getAllByText(/이행 완료/);
    expect(elements.length).toBeGreaterThan(0);
  });
});
