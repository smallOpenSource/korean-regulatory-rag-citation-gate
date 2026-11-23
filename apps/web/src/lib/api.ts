import { useAuthStore } from "../store/auth";
import type { AuthUser, LoginResponse } from "./types";

const DEFAULT_API_BASE_URL = "/api";

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ?? DEFAULT_API_BASE_URL;
export const WS_BASE_URL = (import.meta.env.VITE_WS_BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "/api/ws";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function parseJson(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) {
    return null;
  }
  return JSON.parse(text) as unknown;
}

function applyHeaders(init: RequestInit, token: string | null): Headers {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  return headers;
}

async function refreshSessionToken(): Promise<string> {
  await refreshSessionFromCookie();
  const state = useAuthStore.getState();
  const accessToken = state.accessToken;
  if (!accessToken) {
    throw new ApiError(401, "access_token 없음");
  }
  return accessToken;
}

async function refreshSessionFromCookie(): Promise<void> {
  const state = useAuthStore.getState();
  state.setRestoring(true);
  try {
    const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
      method: "POST",
      credentials: "include",
      headers: applyHeaders({}, null),
    });
    const payload = await parseJson(response);
    if (!response.ok) {
      state.clearSession();
      state.markRestoreFailed();
      throw new ApiError(response.status, response.statusText || "토큰 갱신 실패");
    }
    const accessToken = (payload as LoginResponse | null)?.access_token;
    if (!accessToken) {
      state.clearSession();
      state.markRestoreFailed();
      throw new ApiError(401, "access_token 없음");
    }
    state.setSession({ accessToken, user: normalizeEmployee(payload as LoginResponse, "restored employee") });
  } finally {
    useAuthStore.getState().setRestoring(false);
    useAuthStore.getState().markRestoreAttempted();
  }
}

async function request<T>(path: string, init: RequestInit = {}, allowRefresh = true): Promise<T> {
  const token = useAuthStore.getState().accessToken;
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      credentials: "include",
      headers: applyHeaders(init, token),
    });
  } catch (error) {
    throw new ApiError(0, error instanceof Error ? error.message : "API 연결 실패");
  }

  if (response.status === 401 && allowRefresh && path !== "/auth/login" && path !== "/auth/refresh") {
    await refreshSessionToken();
    return request<T>(path, init, false);
  }

  const payload = await parseJson(response);
  if (!response.ok) {
    const detail = typeof payload === "object" && payload !== null && "detail" in payload ? String(payload.detail) : response.statusText;
    throw new ApiError(response.status, detail || "API 요청 실패");
  }
  return payload as T;
}

function normalizeEmployee(payload: LoginResponse, email: string): AuthUser {
  const employee = payload.employee;
  return {
    employeeId: employee?.id ?? employee?.employee_id ?? "authenticated-employee",
    name: employee?.name ?? email,
    roleCode: employee?.role_code ?? "PB",
    branchId: employee?.branch_id,
  };
}

export async function login(email: string, password: string): Promise<{ accessToken: string; user: AuthUser }> {
  const payload = await request<LoginResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  return {
    accessToken: payload.access_token,
    user: normalizeEmployee(payload, email),
  };
}

export async function restoreSession(): Promise<boolean> {
  const state = useAuthStore.getState();
  if (state.accessToken && state.user) {
    state.markRestoreAttempted();
    return true;
  }
  try {
    await refreshSessionFromCookie();
    return Boolean(useAuthStore.getState().accessToken && useAuthStore.getState().user);
  } catch {
    // T3-2 safety net: refreshSessionFromCookie 내부에서 이미 markRestoreFailed
    // 호출되지만, 예측되지 않은 catch (parseJson 실패 등) 시에도 명시적 fail 신호
    // 유지하여 App.tsx __wmahPageReady 가 stuck되지 않도록 한다.
    useAuthStore.getState().markRestoreFailed();
    return false;
  } finally {
    useAuthStore.getState().markRestoreAttempted();
  }
}

export async function logout(): Promise<void> {
  const token = useAuthStore.getState().accessToken;
  try {
    await fetch(`${API_BASE_URL}/auth/logout`, {
      method: "POST",
      credentials: "include",
      headers: applyHeaders({}, token),
    });
  } catch {
    // Memory session clearing must not be blocked by transient network failures.
  }
}

export async function getResource<T>(path: string): Promise<T> {
  return request<T>(path);
}

export async function postResource<T>(
  path: string,
  body?: unknown,
  options?: { idempotencyKey?: string },
): Promise<T> {
  // ADR-011: state-transition POSTs on email-drafts (submit/approve/reject)
  // and house-views (activate/review/activate-lifecycle) require an
  // Idempotency-Key header. Callers pass a fresh UUID per user-action.
  const init: RequestInit = {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
  };
  if (options?.idempotencyKey) {
    init.headers = { "Idempotency-Key": options.idempotencyKey };
  }
  return request<T>(path, init);
}

export async function patchResource<T>(
  path: string,
  body?: unknown,
  options?: { idempotencyKey?: string },
): Promise<T> {
  const init: RequestInit = {
    method: "PATCH",
    body: body === undefined ? undefined : JSON.stringify(body),
  };
  if (options?.idempotencyKey) {
    init.headers = { "Idempotency-Key": options.idempotencyKey };
  }
  return request<T>(path, init);
}
