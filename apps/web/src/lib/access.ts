import type { RoleCode, RouteKey } from "./types";

// COMPLIANCE_OFFICER (준법감시인) is a read-only cross-domain oversight role: it
// mirrors AUDIT_VIEWER's navigable surface (audit, disputes, conflict-of-interest,
// marketing/KYC/data-governance/consents read pages, AI governance) and additionally
// sees ALL conflict-of-interest disclosures on the server. It performs NO mutation,
// no front-office create, no simulation auto-approve, and is never a 4-eye approver
// (human-handoff control points are preserved). The server RBAC (core/rbac.py +
// per-router gates) is the SoT; rows here must match what the backend permits.
export const ACCESS_RULES: Record<RouteKey, RoleCode[]> = {
  dashboard: ["PB", "WM", "BRANCH_MANAGER", "ADMIN", "AUDIT_VIEWER", "COMPLIANCE_OFFICER"],
  customers: ["PB", "WM", "BRANCH_MANAGER", "ADMIN"],
  customer360: ["PB", "WM", "BRANCH_MANAGER", "ADMIN"],
  consultation: ["PB", "WM"],
  nba: ["PB", "WM"],
  aftercare: ["PB", "WM", "BRANCH_MANAGER", "ADMIN"],
  emailDrafts: ["PB", "WM"],
  houseViews: ["PB", "WM", "BRANCH_MANAGER", "ADMIN", "AUDIT_VIEWER", "COMPLIANCE_OFFICER"],
  houseViewActivation: ["ADMIN"],
  rag: ["PB", "WM", "BRANCH_MANAGER", "ADMIN"],
  batch: ["ADMIN"],
  audit: ["ADMIN", "AUDIT_VIEWER", "COMPLIANCE_OFFICER"],
  auditViewer: ["ADMIN", "AUDIT_VIEWER", "COMPLIANCE_OFFICER"],
  rightsNotice: ["PB", "WM", "BRANCH_MANAGER", "ADMIN"],
  // Observability cycle Item #64 finding (2026-05-23): server-side guard
  // at POST /disputes returns 403 for BRANCH_MANAGER, contradicting the
  // prior client-side claim. Server is the SoT for actual access; BM is
  // removed from the client list to match.
  // tests/test_branch_manager_audit_lane.py::ACCESS_TS_VS_SERVER_DISAGREEMENT
  // tracked this until resolution.
  disputeCase: ["PB", "WM", "ADMIN", "AUDIT_VIEWER", "COMPLIANCE_OFFICER"],
  // Wave-Audit-Defect-Fix C3: backend gates POST on {PB, WM, ADMIN, BRANCH_MANAGER}
  // (routers/conflict_of_interest.py line 96); AUDIT_VIEWER allowed to read.
  conflictOfInterest: ["PB", "WM", "BRANCH_MANAGER", "ADMIN", "AUDIT_VIEWER", "COMPLIANCE_OFFICER"],
  // Wave-Audit-Defect-Fix C4: PB/WM/ADMIN submit; BRANCH_MANAGER+AUDIT_VIEWER
  // can view (the page degrades to a read-only banner for non-write roles).
  marketingReview: ["PB", "WM", "BRANCH_MANAGER", "ADMIN", "AUDIT_VIEWER", "COMPLIANCE_OFFICER"],
  // Wave-Audit-Defect-Fix C5: every staff role sees pseudonym metadata + the
  // purge schedule list; only ADMIN can create new purge entries (gated in
  // the page itself + the backend ADMIN check on POST /purge-schedule).
  // COMPLIANCE_OFFICER excluded: backend _require_admin_or_branch (data_governance.py)
  // denies it; access.ts is kept consistent with the server guard.
  dataGovernance: ["PB", "WM", "BRANCH_MANAGER", "ADMIN", "AUDIT_VIEWER"],
  // Wave-Audit-Defect-Fix C1: every staff role can read consent state; only
  // PB/WM submit grant/withdraw/marketing-stop/bundle (page itself gates).
  // COMPLIANCE_OFFICER excluded: backend _require_staff (consents.py) denies it.
  consents: ["PB", "WM", "BRANCH_MANAGER", "ADMIN", "AUDIT_VIEWER"],
  // Wave-Audit-Defect-Fix C2: PB/WM/ADMIN write (evaluate/reassess/complete);
  // BRANCH_MANAGER + AUDIT_VIEWER read-only list+detail.
  //
  // 2026-05-24 service-readiness v2 cycle finding: backend
  // routers/kyc_edd.py rejects PB with "Compliance role required
  // (ADMIN/WM/BM)". Per the access-rules single-SoT memory rule, the
  // server is authoritative. PB removed from the client list to match.
  // The kyc-edd page is intended for compliance roles, not the
  // front-office PB workflow.
  // COMPLIANCE_OFFICER excluded: backend _require_compliance_role (kyc_edd.py,
  // {ADMIN,WM,BM}) denies it — CO is a read-only role, not a KYC mutator.
  kycEdd: ["WM", "BRANCH_MANAGER", "ADMIN", "AUDIT_VIEWER"],
  aiModelCards: ["PB", "WM", "BRANCH_MANAGER", "ADMIN", "AUDIT_VIEWER", "COMPLIANCE_OFFICER"],
  aiPolicy: ["PB", "WM", "BRANCH_MANAGER", "ADMIN", "AUDIT_VIEWER", "COMPLIANCE_OFFICER"],
  koreanAIAct: ["PB", "WM", "BRANCH_MANAGER", "ADMIN", "AUDIT_VIEWER", "COMPLIANCE_OFFICER"],
  aiAdminDashboard: ["ADMIN"],
  quarantine: ["ADMIN"],
  autopilotDemo: ["PB", "WM", "BRANCH_MANAGER", "ADMIN"],
};

export function canAccessRoute(roleCode: RoleCode, routeKey: RouteKey): boolean {
  return ACCESS_RULES[routeKey].includes(roleCode);
}

export function routeRoles(routeKey: RouteKey): RoleCode[] {
  return ACCESS_RULES[routeKey];
}
