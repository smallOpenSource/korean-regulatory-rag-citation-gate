import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { ApiPanel } from "../components/ApiPanel";
import { getResource } from "../lib/api";
import { formatBankerNumber, formatBankerTimestamp } from "../lib/format";
import { riskGradeLabel, segmentLabel } from "../lib/labels";
import type { ListResponse } from "../lib/types";

interface CustomerRow {
  id: string;
  customer_no?: string;
  customer_name?: string;
  scenario_label?: string;
  segment_code: string;
  risk_grade_code: string;
  total_assets_krw?: number | string;
  last_contacted_at?: string;
  pending_nba_count?: number;
}

export function CustomersPage() {
  const customers = useQuery({ queryKey: ["customers"], queryFn: () => getResource<ListResponse<CustomerRow>>("/customers?limit=20&offset=0") });
  const items = customers.data?.items ?? [];

  return (
    <ApiPanel title="고객 목록" error={customers.error}>
      <div className="overflow-hidden rounded-2xl border border-slate-200">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-left text-xs font-bold uppercase tracking-wide text-slate-500">
            <tr><th className="p-3">고객</th><th className="p-3">세그먼트</th><th className="p-3">위험등급</th><th className="p-3">최종 접촉</th><th className="p-3">미완료 후속 조치</th></tr>
          </thead>
          <tbody className="divide-y divide-slate-100 bg-white">
            {items.map((customer) => (
              <tr key={customer.id}>
                <td className="p-3">
                  <Link className="font-semibold text-blue-700" to={`/customers/${customer.id}`}>
                    {customer.customer_name ?? customer.customer_no ?? customer.id}
                  </Link>
                  {customer.scenario_label && (
                    <div className="mt-0.5 text-xs text-slate-500">{customer.scenario_label}</div>
                  )}
                </td>
                <td className="p-3">{segmentLabel(customer.segment_code)}</td>
                <td className="p-3">{riskGradeLabel(customer.risk_grade_code)}</td>
                <td className="p-3">{formatBankerTimestamp(customer.last_contacted_at)}</td>
                <td className="p-3">{formatBankerNumber(customer.pending_nba_count ?? 0, "건")}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {items.length === 0 ? <p className="p-5 text-sm text-slate-500">표시할 고객이 없습니다. 실제 API 응답과 연결되면 목록이 표시됩니다.</p> : null}
      </div>
    </ApiPanel>
  );
}
