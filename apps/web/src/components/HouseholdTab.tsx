/**
 * HouseholdTab — REG-03 T240
 *
 * Displays 가족관계 (family relationships) and 세대간 자산이전 (inter-generational
 * asset transfer) history inside the Customer 360 view.
 *
 * Data is synthetic-only — no real customer PII is stored or displayed.
 * A persistent watermark is shown at all times.
 */

import { Badge } from "./Badges";
import { KO } from "../lib/i18n";

// ─── Synthetic data types ─────────────────────────────────────────────────────

interface FamilyMember {
  id: string;
  relation: string;
  name: string;
  age: number;
  /** Display string e.g. "35%" */
  assetShareLabel: string;
  /** Numeric 0–100 for progress bar */
  assetSharePct: number;
}

interface AssetTransfer {
  id: string;
  date: string;
  type: string;
  amount: string;
  from: string;
  to: string;
  note?: string;
}

// ─── Synthetic fixtures ───────────────────────────────────────────────────────

const SYNTHETIC_MEMBERS: FamilyMember[] = [
  { id: "m1", relation: "배우자", name: "박○○", age: 61, assetShareLabel: "35%", assetSharePct: 35 },
  { id: "m2", relation: "장남",   name: "김○○", age: 34, assetShareLabel: "20%", assetSharePct: 20 },
  { id: "m3", relation: "장녀",   name: "김○○", age: 31, assetShareLabel: "15%", assetSharePct: 15 },
];

const SYNTHETIC_TRANSFERS: AssetTransfer[] = [
  {
    id: "t1",
    date: "2023-12-15",
    type: KO.household.giftTransfer,
    amount: "15억 원",
    from: "본인",
    to: "장남",
    note: "사전증여공제 한도 내 설계",
  },
  {
    id: "t2",
    date: "2022-08-01",
    type: KO.household.trustTransfer,
    amount: "30억 원",
    from: "본인",
    to: "가족신탁",
    note: "수익자연속신탁 구조",
  },
  {
    id: "t3",
    date: "2021-03-20",
    type: KO.household.giftTransfer,
    amount: "8억 원",
    from: "본인",
    to: "장녀",
    note: "비과세 한도 초과분 과세표준 신고 완료",
  },
];

const TRANSFER_INITIALS: Record<string, string> = {
  [KO.household.giftTransfer]: "증",
  [KO.household.inheritanceTransfer]: "상",
  [KO.household.trustTransfer]: "신",
};

// ─── Sub-components ───────────────────────────────────────────────────────────

function MemberRow({ member }: { member: FamilyMember }) {
  return (
    <tr className="border-b border-slate-50 last:border-0">
      <td className="py-2.5 pr-4 text-sm font-semibold text-slate-700">{member.relation}</td>
      <td className="py-2.5 pr-4 text-sm text-slate-900">{member.name}</td>
      <td className="py-2.5 pr-4 text-sm tabular-nums text-slate-600">{member.age}세</td>
      <td className="py-2.5">
        <div className="flex items-center gap-2">
          <div className="h-1.5 w-20 overflow-hidden rounded-full bg-slate-200">
            {/* dynamic width — cannot express as static Tailwind class */}
            <div
              className="h-full rounded-full bg-blue-600"
              style={{ width: `${member.assetSharePct}%` }}
              role="presentation"
            />
          </div>
          <span className="text-sm tabular-nums text-slate-700">{member.assetShareLabel}</span>
        </div>
      </td>
    </tr>
  );
}

function TransferRow({ transfer }: { transfer: AssetTransfer }) {
  const initial = TRANSFER_INITIALS[transfer.type] ?? "이";
  return (
    <div className="flex items-start justify-between gap-3 rounded-xl bg-slate-50 p-3">
      <div className="flex items-start gap-3">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-100 text-xs font-black text-blue-700">
          {initial}
        </div>
        <div>
          <p className="text-sm font-semibold text-slate-900">
            {transfer.type} · {transfer.from} → {transfer.to}
          </p>
          <p className="text-xs text-slate-500">{transfer.date}</p>
          {transfer.note && (
            <p className="mt-0.5 text-xs text-slate-400">{transfer.note}</p>
          )}
        </div>
      </div>
      <span className="shrink-0 text-sm font-bold tabular-nums text-slate-900">
        {transfer.amount}
      </span>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

interface HouseholdTabProps {
  /** Passed for future API integration; currently serves synthetic data only. */
  customerId: string;
}

export function HouseholdTab({ customerId: _customerId }: HouseholdTabProps) {
  return (
    <div className="grid gap-5">
      {/* Persistent synthetic watermark */}
      <div
        className="flex items-center gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-4"
        role="alert"
        aria-live="polite"
      >
        <span className="text-base" aria-hidden="true">⚠</span>
        <div className="flex flex-1 flex-wrap items-center justify-between gap-2">
          <p className="text-sm font-semibold text-amber-900">
            {KO.household.syntheticNotice}
          </p>
          <Badge tone="orange">합성 데이터</Badge>
        </div>
      </div>

      {/* Policy note */}
      <p className="rounded-xl bg-slate-50 px-4 py-3 text-xs text-slate-600">
        {KO.household.policyNote}
      </p>

      {/* Family members table */}
      <section
        className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
        aria-labelledby="household-members-heading"
      >
        <h3
          id="household-members-heading"
          className="mb-4 text-base font-semibold text-slate-900"
        >
          {KO.household.members}
        </h3>
        {SYNTHETIC_MEMBERS.length === 0 ? (
          <p className="text-sm text-slate-500">{KO.household.noMembers}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full" aria-label={KO.household.members}>
              <thead>
                <tr className="border-b border-slate-100">
                  {[
                    KO.household.relation,
                    KO.household.name,
                    KO.household.age,
                    KO.household.assetShare,
                  ].map((h) => (
                    <th
                      key={h}
                      scope="col"
                      className="py-2 pr-4 text-left text-xs font-bold uppercase tracking-wide text-slate-500"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {SYNTHETIC_MEMBERS.map((member) => (
                  <MemberRow key={member.id} member={member} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Asset transfer history */}
      <section
        className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
        aria-labelledby="household-transfers-heading"
      >
        <h3
          id="household-transfers-heading"
          className="mb-4 text-base font-semibold text-slate-900"
        >
          {KO.household.transferHistory}
        </h3>
        {SYNTHETIC_TRANSFERS.length === 0 ? (
          <p className="text-sm text-slate-500">{KO.household.noTransfers}</p>
        ) : (
          <div className="grid gap-3">
            {SYNTHETIC_TRANSFERS.map((transfer) => (
              <TransferRow key={transfer.id} transfer={transfer} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
