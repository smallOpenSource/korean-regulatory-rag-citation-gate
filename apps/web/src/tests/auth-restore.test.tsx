import { cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { AuthSessionRestorer } from "../App";
import { useAuthStore } from "../store/auth";

/**
 * T3-2 (F14) — App.tsx `__wmahPageReady` 근본 fix 회귀 방지.
 *
 * plan §3 T3-2 fix pattern:
 *   restoreAttempted && (accessToken !== null OR sessionRestoreFailed === true)
 *
 * 이전 cycle (e2ec000 revert 이전) restoreAttempted 단독 조건은 cookie-exchange
 * 완료 *직전*에도 transient state에서 true로 비치는 race를 일으켜 Playwright
 * audit-e2e가 ProtectedRoute /login bounce를 catch했다. 두 path 모두 명시적으로
 * cover하는지 확인한다. ([[bfs-auth-race-window]])
 */

const restoredAdminSession = {
  accessToken: "restored-access-token",
  user: {
    employeeId: "22222222-2222-2222-2222-222222222204",
    name: "테스트 관리자",
    roleCode: "ADMIN" as const,
    branchId: "11111111-1111-1111-1111-111111111101",
  },
};

type PageReadyWindow = Window & { __wmahPageReady?: boolean };

function readPageReady(): boolean | undefined {
  return (window as PageReadyWindow).__wmahPageReady;
}

function resetPageReady(): void {
  delete (window as PageReadyWindow).__wmahPageReady;
}

describe("AuthSessionRestorer __wmahPageReady signal (T3-2 F14)", () => {
  beforeEach(() => {
    resetPageReady();
    // restoreAttempted=true로 시작하여 mount-time restoreSession()이 fetch fire
    // 하지 않도록 short-circuit (store auth.ts:34 분기). 두 보강 조건 모두 false
    // 이므로 effect는 ready 신호를 set하지 않는다.
    useAuthStore.setState({
      accessToken: null,
      user: null,
      isRestoring: false,
      restoreAttempted: true,
      sessionRestoreFailed: false,
    });
  });

  afterEach(() => {
    cleanup();
    resetPageReady();
  });

  it("success path: setSession 호출 시 restoreAttempted=true + accessToken!==null → __wmahPageReady=true", async () => {
    render(<AuthSessionRestorer />);

    useAuthStore.getState().setSession(restoredAdminSession);

    await waitFor(() => {
      expect(readPageReady()).toBe(true);
    });

    const state = useAuthStore.getState();
    expect(state.restoreAttempted).toBe(true);
    expect(state.accessToken).toBe("restored-access-token");
    expect(state.sessionRestoreFailed).toBe(false);
  });

  it("failure path: markRestoreFailed 호출 시 restoreAttempted=true + sessionRestoreFailed=true → __wmahPageReady=true", async () => {
    render(<AuthSessionRestorer />);

    useAuthStore.getState().markRestoreFailed();

    await waitFor(() => {
      expect(readPageReady()).toBe(true);
    });

    const state = useAuthStore.getState();
    expect(state.restoreAttempted).toBe(true);
    expect(state.accessToken).toBeNull();
    expect(state.sessionRestoreFailed).toBe(true);
  });

  it("regression negative: restoreAttempted만 true이고 accessToken=null + sessionRestoreFailed=false → __wmahPageReady 미발사", async () => {
    // svc-viability-v2 T3-2 fix 이전 단독 condition (markRestoreAttempted) 단독 호출:
    // accessToken=null이지만 sessionRestoreFailed도 false인 transient state에서
    // ready 신호가 잘못 발사되지 않음을 확인 (race 회피).
    render(<AuthSessionRestorer />);

    useAuthStore.getState().markRestoreAttempted();

    // restoreAttempted=true이지만 두 보강 조건 모두 false → ready 미발사 유지
    await new Promise((resolve) => setTimeout(resolve, 30));

    expect(readPageReady()).toBeUndefined();

    const state = useAuthStore.getState();
    expect(state.restoreAttempted).toBe(true);
    expect(state.accessToken).toBeNull();
    expect(state.sessionRestoreFailed).toBe(false);
  });
});
