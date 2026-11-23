import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { useAuthStore } from "../store/auth";

const pbSession = {
  accessToken: "access-token",
  user: {
    employeeId: "22222222-2222-2222-2222-222222222201",
    name: "테스트 PB",
    roleCode: "PB" as const,
    branchId: "11111111-1111-1111-1111-111111111101",
  },
};

describe("auth session boundary", () => {
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
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  it("keeps refresh tokens outside browser JavaScript state and storage", () => {
    useAuthStore.getState().setSession(pbSession);

    expect(useAuthStore.getState().accessToken).toBe("access-token");
    expect(useAuthStore.getState().user?.employeeId).toBe(pbSession.user.employeeId);
    expect("refreshToken" in useAuthStore.getState()).toBe(false);
    expect(Object.keys(window.localStorage)).toEqual([]);
    expect(Object.keys(window.sessionStorage)).toEqual([]);
  });

  it("keeps the auth API source on the HttpOnly-cookie refresh boundary", async () => {
    const { readFile } = await import("node:fs/promises");
    const { join } = await import("node:path");
    const source = await readFile(join(process.cwd(), "src/lib/api.ts"), "utf8");

    expect(source).toContain('"/auth/refresh"');
    expect(source).toContain('credentials: "include"');
    expect(source).not.toContain("refreshToken");
    expect(source).not.toContain("localStorage");
    expect(source).not.toContain("sessionStorage");
  });
});
