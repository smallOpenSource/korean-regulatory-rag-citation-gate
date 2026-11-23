import type { ReactNode } from "react";

import { ApiError } from "../lib/api";

const STATUS_KO: Record<number, string> = {
  400: "요청 형식이 올바르지 않습니다.",
  401: "로그인이 필요합니다.",
  403: "이 정보를 열람할 권한이 없습니다.",
  404: "요청하신 데이터를 찾을 수 없습니다.",
  409: "데이터 충돌이 발생했습니다.",
  422: "요청 데이터 형식이 올바르지 않습니다.",
  429: "요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.",
  500: "서버 오류가 발생했습니다.",
  502: "서버 게이트웨이에 연결할 수 없습니다.",
  503: "서비스를 일시적으로 사용할 수 없습니다.",
  504: "서버 응답이 지연되고 있습니다.",
};

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (STATUS_KO[error.status]) return STATUS_KO[error.status];
    if (error.status === 0) return "네트워크 연결을 확인해 주세요.";
  }
  return "데이터를 불러오지 못했습니다.";
}

export function ApiPanel({ title, error, children }: { title: string; error?: unknown; children: ReactNode }) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold text-slate-950">{title}</h2>
        <span className="text-xs font-medium text-slate-500">실시간 API 연동</span>
      </div>
      {error ? <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-800">{errorMessage(error)}</p> : children}
    </section>
  );
}
