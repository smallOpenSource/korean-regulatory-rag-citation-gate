import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { logout } from "../lib/api";
import { canAccessRoute } from "../lib/access";
import type { RoleCode, RouteKey } from "../lib/types";
import { useAuthStore } from "../store/auth";

interface NavItem { to: string; label: string; routeKey: RouteKey; group?: string }

const NAV_ITEMS: NavItem[] = [
  { to: "/dashboard", label: "대시보드", routeKey: "dashboard" },
  { to: "/customers", label: "고객 목록", routeKey: "customers" },
  { to: "/consultations/new", label: "상담 워크스페이스", routeKey: "consultation" },
  { to: "/nba", label: "후속 조치 (오늘)", routeKey: "nba" },
  { to: "/aftercare", label: "사후관리 (분기)", routeKey: "aftercare" },
  { to: "/email-drafts", label: "이메일 초안", routeKey: "emailDrafts" },
  { to: "/house-views", label: "하우스뷰", routeKey: "houseViews" },
  { to: "/rag", label: "RAG 질의응답", routeKey: "rag" },
  { to: "/batch", label: "배치 모니터링", routeKey: "batch" },
  { to: "/quarantine", label: "격리 대시보드", routeKey: "quarantine" },
  { to: "/audit", label: "감사 로그", routeKey: "audit", group: "거버넌스" },
  { to: "/audit-viewer", label: "감사 열람 (고급)", routeKey: "auditViewer", group: "거버넌스" },
  { to: "/rights-notice", label: "소비자 권리 고지", routeKey: "rightsNotice", group: "거버넌스" },
  { to: "/dispute-cases", label: "분쟁 조정", routeKey: "disputeCase", group: "거버넌스" },
  { to: "/ai-model-cards", label: "AI 모델 카드", routeKey: "aiModelCards", group: "AI 거버넌스" },
  { to: "/ai-policy", label: "AI 사용 정책", routeKey: "aiPolicy", group: "AI 거버넌스" },
  { to: "/korean-ai-act", label: "인공지능기본법", routeKey: "koreanAIAct", group: "AI 거버넌스" },
  { to: "/ai-admin-dashboard", label: "AI 운영현황", routeKey: "aiAdminDashboard", group: "AI 거버넌스" },
];

const ROLE_LABELS: Record<RoleCode, string> = {
  PB: "PB 담당자",
  WM: "WM 담당자",
  BRANCH_MANAGER: "지점 관리자",
  ADMIN: "시스템 관리자",
  AUDIT_VIEWER: "감사 열람자",
  COMPLIANCE_OFFICER: "준법감시인",
};

function NavGroup({ label, items }: { label?: string; items: NavItem[] }) {
  return (
    <div className="grid gap-1">
      {label && (
        <p className="mt-3 mb-1 px-3 text-[10px] font-bold uppercase tracking-[0.2em] text-slate-400">
          {label}
        </p>
      )}
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          className={({ isActive }) =>
            `rounded-xl px-3 py-2 text-sm font-semibold ${isActive ? "bg-blue-700 text-white" : "text-slate-600 hover:bg-slate-100"}`
          }
        >
          {item.label}
        </NavLink>
      ))}
    </div>
  );
}

export function Layout() {
  const navigate = useNavigate();
  const user = useAuthStore((state) => state.user);
  const clearSession = useAuthStore((state) => state.clearSession);
  const visibleNavItems = user ? NAV_ITEMS.filter((item) => canAccessRoute(user.roleCode, item.routeKey)) : [];

  // Split into ungrouped + grouped sections
  const ungrouped = visibleNavItems.filter((i) => !i.group);
  const groupMap = new Map<string, NavItem[]>();
  for (const item of visibleNavItems.filter((i) => i.group)) {
    const key = item.group!;
    const existing = groupMap.get(key) ?? [];
    groupMap.set(key, [...existing, item]);
  }

  return (
    <div className="min-h-screen bg-slate-100 text-slate-950">
      <aside className="fixed inset-y-0 left-0 hidden w-64 overflow-y-auto border-r border-slate-200 bg-white p-6 pb-8 lg:block">
        <div className="mb-8">
          <p className="text-xs font-bold uppercase tracking-[0.25em] text-blue-700">Harness</p>
          <h1 className="mt-2 text-xl font-black">PB/WM AI 업무지원</h1>
        </div>
        <nav aria-label="주 메뉴" className="grid gap-1">
          <NavGroup items={ungrouped} />
          {Array.from(groupMap.entries()).map(([group, items]) => (
            <NavGroup key={group} label={group} items={items} />
          ))}
        </nav>
      </aside>
      <div className="lg:pl-64">
        <header className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-200 bg-white/90 px-6 py-4 backdrop-blur">
          <div>
            <p className="text-sm font-medium text-slate-500">내부 직원 전용 · AI 의사결정 보조</p>
            <p className="text-base font-bold text-slate-900">{user?.name ?? "미인증 사용자"} · {user?.roleCode ? ROLE_LABELS[user.roleCode] ?? user.roleCode : "권한 미확인"}</p>
          </div>
          <button
            type="button"
            onClick={async () => {
              try {
                await logout();
              } finally {
                clearSession();
                navigate("/login");
              }
            }}
            className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700"
          >
            로그아웃
          </button>
        </header>
        <main className="mx-auto max-w-7xl p-6">
          <p
            data-test="synthetic-watermark"
            className="mb-4 rounded-full border border-amber-200 bg-amber-50 px-3 py-1.5 text-center text-xs font-bold text-amber-900"
          >
            합성 데이터 데모 환경 · 실제 고객 정보가 아닙니다.
          </p>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
