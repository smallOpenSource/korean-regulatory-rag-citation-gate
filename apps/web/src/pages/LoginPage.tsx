import { useEffect, useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useLocation, useNavigate } from "react-router-dom";

import { ApiError, login } from "../lib/api";
import { useAuthStore } from "../store/auth";

function loginErrorMessage(error: unknown): string {
  if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
    return "이메일 또는 비밀번호를 확인하세요.";
  }
  if (error instanceof ApiError && error.status === 0) {
    return "서버에 연결하지 못했습니다. 네트워크 또는 API 상태를 확인하세요.";
  }
  return "로그인을 완료하지 못했습니다. 잠시 후 다시 시도하세요.";
}

function loginRedirectTarget(locationState: unknown): string {
  if (typeof locationState === "object" && locationState && "from" in locationState) {
    const target = String(locationState.from);
    if (target.startsWith("/") && target !== "/login") {
      return target;
    }
  }
  return "/dashboard";
}

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const setSession = useAuthStore((state) => state.setSession);
  const accessToken = useAuthStore((state) => state.accessToken);
  const user = useAuthStore((state) => state.user);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const redirectTarget = useMemo(() => loginRedirectTarget(location.state), [location.state]);

  useEffect(() => {
    if (accessToken && user) {
      navigate(redirectTarget, { replace: true });
    }
  }, [accessToken, navigate, redirectTarget, user]);

  const mutation = useMutation({
    mutationFn: () => login(email, password),
    onSuccess: (session) => {
      setSession(session);
      navigate(redirectTarget, { replace: true });
    },
  });

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-950 px-6 text-white">
      <section className="w-full max-w-md rounded-3xl border border-white/10 bg-white/10 p-8 shadow-2xl backdrop-blur">
        <p className="text-sm font-bold uppercase tracking-[0.3em] text-blue-200">Harness</p>
        <h1 className="mt-3 text-3xl font-black">직원 로그인</h1>
        <p className="mt-3 text-sm text-slate-200">접속 토큰은 브라우저 저장소에 남기지 않습니다. 인증이 필요하면 직원 확인 후 요청했던 화면으로 이동합니다.</p>
        <p className="mt-3 rounded-xl bg-blue-500/20 p-3 text-sm text-blue-50">보호된 화면입니다. 직원 인증 후 이어서 이용하세요.</p>
        <form
          className="mt-8 grid gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            mutation.mutate();
          }}
        >
          <label className="grid gap-2 text-sm font-semibold">
            이메일
            <input className="rounded-xl border border-white/20 bg-white px-4 py-3 text-slate-950" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
          </label>
          <label className="grid gap-2 text-sm font-semibold">
            비밀번호
            <input className="rounded-xl border border-white/20 bg-white px-4 py-3 text-slate-950" type="password" value={password} onChange={(event) => setPassword(event.target.value)} required />
          </label>
          {mutation.error ? <p role="alert" className="rounded-xl bg-red-500/20 p-3 text-sm text-red-100">{loginErrorMessage(mutation.error)}</p> : null}
          <button className="rounded-xl bg-blue-500 px-4 py-3 font-bold text-white disabled:opacity-60" type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? "인증 중" : "로그인"}
          </button>
        </form>
      </section>
    </main>
  );
}
