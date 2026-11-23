import { Link } from "react-router-dom";

export function ForbiddenPage() {
  return <main className="flex min-h-screen items-center justify-center bg-slate-100 p-6"><section className="rounded-3xl bg-white p-8 text-center shadow-sm"><h1 className="text-3xl font-black text-slate-950">403</h1><p className="mt-3 text-slate-600">권한이 없습니다.</p><Link className="mt-5 inline-flex rounded-xl bg-blue-700 px-4 py-2 text-sm font-bold text-white" to="/dashboard">대시보드</Link></section></main>;
}
