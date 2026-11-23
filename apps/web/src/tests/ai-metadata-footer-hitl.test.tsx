/**
 * ai-metadata-footer-hitl.test.tsx — P1-c HITL UI (2026-05-30).
 *
 * The shared AIMetadataFooter must surface the P0 quality signals so a PB/WM
 * reviewer sees them before acting on an AI output:
 *   - data_quality_notice (synthetic/unverified disclosure)
 *   - faithfulness (passed → 확인 / flags → 검토 필요 + flag labels + ungrounded figures)
 *   - _pii_masked_categories (structured PII auto-masked at the output boundary)
 *
 * No request-mocking or test-double library is used — the project contract
 * test_no_frontend_test_double_helpers_in_checked_in_tests forbids them. Instead
 * the footer's react-query cache key ["ai-output", id] is pre-seeded so useQuery
 * resolves from cache with no network call.
 */

import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { AIMetadataFooter } from "../components/AIMetadataFooter";

afterEach(cleanup);

function renderWithOutput(id: string, output: Record<string, unknown>) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  // Pre-seed the footer's query cache so useQuery resolves from cache (no fetch,
  // no test-double helper). staleTime keeps it fresh so the queryFn is not called.
  qc.setQueryData(["ai-output", id], output);
  return render(
    <QueryClientProvider client={qc}>
      <AIMetadataFooter ai_output_id={id} />
    </QueryClientProvider>,
  );
}

describe("P1-c HITL: AIMetadataFooter surfaces P0 quality signals", () => {
  it("renders disclosure + review-needed faithfulness + ungrounded figure + PII mask", async () => {
    renderWithOutput("out-1", {
      id: "out-1",
      generated_at: "2026-05-30T10:00:00Z",
      model_name: "gpt-5.5",
      output_json: {
        data_quality_notice: "[데이터 품질 고지] 합성·미검증 데이터 기반입니다.",
        faithfulness: {
          method: "deterministic_v1",
          has_disclosure: true,
          ungrounded_figures: ["3.2%"],
          flags: ["UNGROUNDED_FIGURES"],
          passed: false,
        },
        _pii_masked_categories: ["rrn", "mobile"],
      },
    });

    await waitFor(() => expect(screen.getByTestId("ai-data-quality-notice")).toBeTruthy());
    expect(screen.getByTestId("ai-data-quality-notice").textContent).toContain("합성·미검증");

    const faithful = screen.getByTestId("ai-faithfulness").textContent ?? "";
    expect(faithful).toContain("검토 필요");
    expect(faithful).toContain("미근거 수치");
    expect(faithful).toContain("3.2%");

    expect(screen.getByTestId("ai-pii-masked").textContent).toContain("rrn");
    expect(screen.getByTestId("ai-pii-masked").textContent).toContain("mobile");
  });

  it("renders faithfulness 확인 when passed and omits notice/pii blocks when absent", async () => {
    renderWithOutput("out-2", {
      id: "out-2",
      generated_at: "2026-05-30T10:00:00Z",
      model_name: "gpt-5-mini",
      output_json: {
        faithfulness: {
          method: "deterministic_v1",
          has_disclosure: true,
          ungrounded_figures: [],
          flags: [],
          passed: true,
        },
      },
    });

    await waitFor(() => expect(screen.getByTestId("ai-faithfulness")).toBeTruthy());
    expect(screen.getByTestId("ai-faithfulness").textContent).toContain("확인");
    expect(screen.queryByTestId("ai-data-quality-notice")).toBeNull();
    expect(screen.queryByTestId("ai-pii-masked")).toBeNull();
  });
});
