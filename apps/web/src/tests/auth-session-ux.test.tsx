import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { LoginPage } from "../pages/LoginPage";
import { ProtectedRoute } from "../components/ProtectedRoute";
import { useAuthStore } from "../store/auth";

const restoredAdminSession = {
  accessToken: "restored-access-token",
  user: {
    employeeId: "22222222-2222-2222-2222-222222222204",
    name: "테스트 관리자",
    roleCode: "ADMIN" as const,
    branchId: "11111111-1111-1111-1111-111111111101",
  },
};

function renderLoginRoute(state?: unknown) {
  const queryClient = new QueryClient({
    defaultOptions: {
      mutations: { retry: false },
      queries: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[{ pathname: "/login", state }]}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/dashboard" element={<h1>대시보드</h1>} />
          <Route path="/batch" element={<h1>배치 모니터링</h1>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function renderProtectedBatchRoute() {
  return render(
    <MemoryRouter initialEntries={["/batch"]}>
      <Routes>
        <Route
          path="/batch"
          element={
            <ProtectedRoute routeKey="batch">
              <h1>배치 모니터링</h1>
            </ProtectedRoute>
          }
        />
        <Route path="/login" element={<h1>직원 로그인</h1>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("login session UX", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
    useAuthStore.setState({
      accessToken: null,
      user: null,
      isRestoring: false,
      restoreAttempted: false,
    });
  });

  afterEach(() => {
    cleanup();
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  it("redirects an already-restored employee from login to the protected target", async () => {
    useAuthStore.getState().setSession(restoredAdminSession);

    renderLoginRoute({ from: "/batch" });

    expect(await screen.findByRole("heading", { name: "배치 모니터링" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "직원 로그인" })).not.toBeInTheDocument();
    expect(Object.keys(window.localStorage)).toEqual([]);
    expect(Object.keys(window.sessionStorage)).toEqual([]);
  });

  it("keeps unauthenticated employees on Korean login guidance", () => {
    renderLoginRoute();

    expect(screen.getByRole("heading", { name: "직원 로그인" })).toBeInTheDocument();
    expect(screen.getByText(/접속 토큰은 브라우저 저장소에 남기지 않습니다/)).toBeInTheDocument();
  });

  it("keeps protected reloads on Korean session-restore guidance before redirecting", () => {
    useAuthStore.setState({
      accessToken: null,
      user: null,
      isRestoring: false,
      restoreAttempted: false,
    });

    renderProtectedBatchRoute();

    expect(screen.getByText("인증 세션을 확인하는 중입니다.")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "배치 모니터링" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "직원 로그인" })).not.toBeInTheDocument();
  });

  it("resumes protected admin screens after reload restoration rebuilds memory auth", () => {
    useAuthStore.getState().setSession(restoredAdminSession);

    renderProtectedBatchRoute();

    expect(screen.getByRole("heading", { name: "배치 모니터링" })).toBeInTheDocument();
    expect(Object.keys(window.localStorage)).toEqual([]);
    expect(Object.keys(window.sessionStorage)).toEqual([]);
  });
});
