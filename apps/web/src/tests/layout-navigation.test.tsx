import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { Layout } from "../components/Layout";
import type { RoleCode } from "../lib/types";
import { useAuthStore } from "../store/auth";

function setEmployeeSession(roleCode: RoleCode) {
  useAuthStore.setState({
    accessToken: "access-token",
    user: {
      employeeId: `employee-${roleCode}`,
      name: `${roleCode} 직원`,
      roleCode,
      branchId: "branch-1",
    },
    isRestoring: false,
    restoreAttempted: true,
  });
}

function renderLayout(roleCode: RoleCode) {
  setEmployeeSession(roleCode);

  render(
    <MemoryRouter initialEntries={["/dashboard"]}>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/dashboard" element={<h2>대시보드 본문</h2>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );

  return screen.getByRole("navigation");
}

describe("role-aware Korean navigation", () => {
  beforeEach(() => {
    useAuthStore.setState({
      accessToken: null,
      user: null,
      isRestoring: false,
      restoreAttempted: false,
    });
  });

  afterEach(() => {
    cleanup();
    useAuthStore.setState({
      accessToken: null,
      user: null,
      isRestoring: false,
      restoreAttempted: false,
    });
  });

  it("shows PB/WM workflow links without admin-only screens", () => {
    const nav = renderLayout("PB");

    expect(within(nav).getByRole("link", { name: "고객 목록" })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "상담 워크스페이스" })).toBeInTheDocument();
    // Layout label is "후속 조치 (오늘)"; use regex matcher for partial accessibility name.
    expect(within(nav).getByRole("link", { name: /후속 조치/ })).toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: "배치 모니터링" })).not.toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: "감사 로그" })).not.toBeInTheDocument();
  });

  it("hides PB/WM-only action links from admin navigation", () => {
    const nav = renderLayout("ADMIN");

    expect(within(nav).getByRole("link", { name: "배치 모니터링" })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "감사 로그" })).toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: "상담 워크스페이스" })).not.toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: /후속 조치/ })).not.toBeInTheDocument();
  });

  it("keeps audit viewers on read-only navigation", () => {
    const nav = renderLayout("AUDIT_VIEWER");

    expect(within(nav).getByRole("link", { name: "대시보드" })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "하우스뷰" })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "감사 로그" })).toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: "고객 목록" })).not.toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: "RAG 질의응답" })).not.toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: "배치 모니터링" })).not.toBeInTheDocument();
  });
});
