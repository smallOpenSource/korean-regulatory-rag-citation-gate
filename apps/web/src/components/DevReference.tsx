/**
 * DevReference — render internal identifiers (ADR-###, W#-T#, REG-0#, §x.y, etc.)
 * only for ADMIN role. Hidden completely for PB/WM/BRANCH_MANAGER/AUDIT_VIEWER.
 *
 * Use this whenever a Korean copy string would otherwise leak an internal taxonomy
 * tag onto a customer-facing or front-office staff surface.
 *
 * Note: AUDIT_VIEWER is intentionally excluded — compliance reviewers work with
 * audit logs and do not require developer architecture references (ADR/REG).
 * visual-fullwalk spec checks AUDIT_VIEWER against BANNED_INTERNAL_ID, so
 * exposing ADR/REG to AUDIT_VIEWER would cause spec failures.
 */
import type { ReactNode } from "react";

import { useAuthStore } from "../store/auth";

export interface DevReferenceProps {
  inline?: string;
  children?: ReactNode;
  className?: string;
}

const ALLOWED_ROLES = new Set(["ADMIN"]);

export function DevReference({ inline, children, className }: DevReferenceProps): JSX.Element | null {
  const roleCode = useAuthStore((state) => state.user?.roleCode);
  if (!roleCode || !ALLOWED_ROLES.has(roleCode)) {
    return null;
  }
  const content = children ?? inline;
  if (content === null || content === undefined || content === "") {
    return null;
  }
  return (
    <span
      data-test="dev-reference"
      className={
        className ??
        "ml-1 inline-block rounded border border-slate-300 bg-slate-50 px-1.5 py-0.5 align-middle text-[10px] font-bold uppercase tracking-wider text-slate-500"
      }
      title="내부 참조 식별자 (관리/감사 전용)"
    >
      {content}
    </span>
  );
}
