import { create } from "zustand";

import type { AuthUser } from "../lib/types";

interface AuthState {
  accessToken: string | null;
  user: AuthUser | null;
  isRestoring: boolean;
  restoreAttempted: boolean;
  // T3-2 (F14): "session restore failure" 명시 flag. App.tsx `__wmahPageReady`
  // signal이 accessToken!==null OR sessionRestoreFailed===true 두 path 모두
  // cover하도록 사용. setSession() success 시 자동 reset, markRestoreFailed()
  // failure 시 true. ([[bfs-auth-race-window]] 회피)
  sessionRestoreFailed: boolean;
  setSession: (session: { accessToken: string; user: AuthUser }) => void;
  clearSession: () => void;
  setRestoring: (isRestoring: boolean) => void;
  markRestoreAttempted: () => void;
  markRestoreFailed: () => void;
  restoreSession: () => Promise<boolean>;
}

let restoreSessionPromise: Promise<boolean> | null = null;

export const useAuthStore = create<AuthState>((set, get) => ({
  accessToken: null,
  user: null,
  isRestoring: false,
  restoreAttempted: false,
  sessionRestoreFailed: false,
  setSession: ({ accessToken, user }) =>
    set({ accessToken, user, restoreAttempted: true, sessionRestoreFailed: false }),
  clearSession: () => set({ accessToken: null, user: null, restoreAttempted: true }),
  setRestoring: (isRestoring) => set({ isRestoring }),
  markRestoreAttempted: () => set({ restoreAttempted: true }),
  markRestoreFailed: () => set({ restoreAttempted: true, sessionRestoreFailed: true }),
  restoreSession: () => {
    const state = get();
    if (state.accessToken && state.user) {
      state.markRestoreAttempted();
      return Promise.resolve(true);
    }
    if (state.restoreAttempted) {
      return Promise.resolve(false);
    }
    if (restoreSessionPromise) {
      return restoreSessionPromise;
    }

    restoreSessionPromise = import("../lib/api")
      .then(({ restoreSession }) => restoreSession())
      .finally(() => {
        restoreSessionPromise = null;
      });
    return restoreSessionPromise;
  },
}));

// Audit-e2e accessor (DEV mode only). The Playwright `freshLogin`
// helper polls `window.__wmahAuth?.accessToken` to detect that the
// post-login setSession() commit has happened, eliminating the JTI
// race documented in [[bfs-auth-race-window]]. Gated behind the Vite
// DEV flag so the helper is stripped from production bundles.
if (import.meta.env.DEV) {
  (window as unknown as { __wmahAuth?: { getAccessToken: () => string | null } }).__wmahAuth = {
    getAccessToken: () => useAuthStore.getState().accessToken,
  };
}
