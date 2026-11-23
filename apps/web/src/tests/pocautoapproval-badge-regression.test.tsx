/**
 * pocautoapproval-badge-regression.test.tsx — T306 screenshot regression.
 *
 * T306 BACKLOG: "UI `PoC AUTO APPROVAL · 데모 모드` 배지 + 상세 메시지 +
 * aria 속성 + screenshot 회귀"
 *
 * a11y aspects are covered in a11y.test.tsx; this file owns the snapshot
 * (rendered-DOM) regression baseline so future refactors of the badge
 * surface (sticky banner + modal) cannot silently drift its visible text
 * or aria semantics without triggering a diff.
 */

import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { PoCAutoApprovalBadge } from "../components/PoCAutoApprovalBadge";

afterEach(cleanup);

describe("PoCAutoApprovalBadge T306 screenshot regression", () => {
  it("renders zero output when disabled (production guard)", () => {
    const { container } = render(<PoCAutoApprovalBadge enabled={false} />);
    expect(container.innerHTML).toBe("");
  });

  it("sticky banner DOM snapshot — enabled state", () => {
    const { container } = render(<PoCAutoApprovalBadge enabled={true} />);
    const banner = container.querySelector('[role="banner"]');
    expect(banner).not.toBeNull();
    expect(banner!.outerHTML).toMatchSnapshot("banner-enabled");
  });

  it("banner text contains canonical warning string", () => {
    render(<PoCAutoApprovalBadge enabled={true} />);
    expect(
      screen.getByText(/PoC AUTO APPROVAL MODE — 프로덕션에서는 차단됩니다/),
    ).toBeInTheDocument();
  });

  it("banner has aria-label declaring 데모 모드 경고 context", () => {
    render(<PoCAutoApprovalBadge enabled={true} />);
    const banner = screen.getByRole("banner");
    expect(banner).toHaveAttribute(
      "aria-label",
      "PoC 자동 승인 모드 활성화 경고",
    );
  });

  it("ADR-004 참조 button has aria-haspopup=dialog", () => {
    render(<PoCAutoApprovalBadge enabled={true} />);
    const btn = screen.getByRole("button", { name: "ADR-004 참조" });
    expect(btn).toHaveAttribute("aria-haspopup", "dialog");
    expect(btn).toHaveAttribute("aria-expanded", "false");
  });

  it("modal DOM snapshot — open state", () => {
    render(<PoCAutoApprovalBadge enabled={true} />);
    const trigger = screen.getByRole("button", { name: "ADR-004 참조" });
    fireEvent.click(trigger);
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAttribute("aria-label", "ADR-004 PoC 자동 승인 증명");
    expect(dialog.outerHTML).toMatchSnapshot("dialog-open");
  });

  it("modal body references ADR-004 §3 dead-code-elimination guarantee", () => {
    render(<PoCAutoApprovalBadge enabled={true} />);
    fireEvent.click(screen.getByRole("button", { name: "ADR-004 참조" }));
    expect(
      screen.getByText(/프로덕션 빌드에서는 이 핸들러가 dead-code-eliminated 됩니다/),
    ).toBeInTheDocument();
  });

  it("modal closes on ✕ button", () => {
    render(<PoCAutoApprovalBadge enabled={true} />);
    fireEvent.click(screen.getByRole("button", { name: "ADR-004 참조" }));
    expect(screen.queryByRole("dialog")).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "닫기" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("button aria-expanded flips to true when modal opens", () => {
    render(<PoCAutoApprovalBadge enabled={true} />);
    const trigger = screen.getByRole("button", { name: "ADR-004 참조" });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
  });
});
