import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { canAccessRoute } from "../lib/access";
import type { RouteKey } from "../lib/types";
import { useAuthStore } from "../store/auth";

export function ProtectedRoute({ routeKey, children }: { routeKey: RouteKey; children: ReactNode }) {
  const location = useLocation();
  const user = useAuthStore((state) => state.user);
  const accessToken = useAuthStore((state) => state.accessToken);
  const isRestoring = useAuthStore((state) => state.isRestoring);
  const restoreAttempted = useAuthStore((state) => state.restoreAttempted);

  if ((!user || !accessToken) && (isRestoring || !restoreAttempted)) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-950 px-6 text-white">
        <p className="rounded-2xl border border-white/10 bg-white/10 px-5 py-4 text-sm font-semibold">
          인증 세션을 확인하는 중입니다.
        </p>
      </main>
    );
  }

  if (!user || !accessToken) {
    return <Navigate to="/login" replace state={{ from: `${location.pathname}${location.search}` }} />;
  }
  if (!canAccessRoute(user.roleCode, routeKey)) {
    return <Navigate to="/403" replace />;
  }
  return <>{children}</>;
}
