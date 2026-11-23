/**
 * Left pane of ConsultationPage — customer 360 summary.
 * Extracted during Stage 2 T28 split (DEV-02). Behavior unchanged.
 */
import { useQuery } from "@tanstack/react-query";

import { ApiError, getResource } from "../lib/api";
import { formatKRW } from "../lib/format";
import { KO } from "../lib/i18n";
import { segmentLabel, riskGradeLabel } from "../lib/labels";
import type { SyntheticCustomerNotice } from "../lib/types";
import type { CustomerSummary } from "./ConsultationPaneTypes";

export function ConsultationCustomerSummaryPane({ customerId }: { customerId: string | null }) {
  const { data, error, isLoading } = useQuery({
    queryKey: ["customer-summary", customerId],
    queryFn: () =>
      getResource<{ customer?: CustomerSummary; synthetic_customer_notice?: SyntheticCustomerNotice }>(
        `/customers/${customerId}`,
      ),
    enabled: Boolean(customerId),
  });

  const customer = data?.customer;
  const notice = data?.synthetic_customer_notice ?? customer?.synthetic_customer_notice;

  return (
    <div className="grid gap-3 p-1 pr-2">
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-base font-semibold text-slate-900">{KO.consultation.customerSummary}</h2>

        {!customerId && (
          <p className="mt-3 text-xs text-slate-500">{KO.consultation.selectCustomer}</p>
        )}

        {customerId && isLoading && (
          <p className="mt-3 text-xs text-slate-400">고객 정보 불러오는 중…</p>
        )}

        {customerId && error && (
          <p className="mt-3 text-xs text-amber-800">
            {error instanceof ApiError ? error.message : "고객 정보를 불러오지 못했습니다."}
          </p>
        )}

        {notice && (
          <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs font-semibold text-amber-900">
            {KO.ai.syntheticWatermark}
          </div>
        )}

        {customer && (
          <div className="mt-3 grid gap-2">
            {[
              { label: "성명", value: customer.customer_name ?? customer.customer_no ?? customer.id },
              { label: "시나리오", value: customer.scenario_label ?? "—" },
              { label: "세그먼트", value: segmentLabel(customer.segment_code) },
              { label: "위험등급", value: riskGradeLabel(customer.risk_grade_code) },
              {
                label: "총자산",
                value: formatKRW(customer.total_assets_krw),
              },
            ].map(({ label, value }) => (
              <div key={label} className="rounded-xl bg-slate-50 px-3 py-2.5">
                <p className="text-xs font-bold uppercase text-slate-400">{label}</p>
                <p className="mt-0.5 text-sm font-semibold text-slate-900">{value}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
