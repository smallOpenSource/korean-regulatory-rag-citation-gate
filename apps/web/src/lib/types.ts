export type RoleCode =
  | "PB"
  | "WM"
  | "BRANCH_MANAGER"
  | "ADMIN"
  | "AUDIT_VIEWER"
  | "COMPLIANCE_OFFICER";

export type RouteKey =
  | "dashboard"
  | "customers"
  | "customer360"
  | "consultation"
  | "nba"
  | "aftercare"
  | "emailDrafts"
  | "houseViews"
  | "houseViewActivation"
  | "rag"
  | "batch"
  | "audit"
  | "auditViewer"
  | "rightsNotice"
  | "disputeCase"
  | "conflictOfInterest"
  | "marketingReview"
  | "dataGovernance"
  | "consents"
  | "kycEdd"
  | "aiModelCards"
  | "aiPolicy"
  | "koreanAIAct"
  | "aiAdminDashboard"
  | "quarantine"
  | "autopilotDemo";

export interface AuthUser {
  employeeId: string;
  name: string;
  roleCode: RoleCode;
  branchId?: string;
}

export interface LoginResponse {
  access_token: string;
  employee?: {
    id?: string;
    employee_id?: string;
    name?: string;
    role_code?: RoleCode;
    branch_id?: string;
  };
}

export interface ApiErrorShape {
  status: number;
  message: string;
}

export interface AiOutputMetadata {
  generatedAt: string;
  modelName: string;
}

export interface RecommendationGateState {
  suitabilityPassed: boolean;
  explanationChecked: boolean;
  simulatedCustomerConsented: boolean;
  employeeFinalApproved: boolean;
}

export interface WebSocketEvent {
  event_type:
    | "connection_ack"
    | "pong"
    | "error"
    | "nba_created"
    | "nba_updated"
    | "ai_job_done"
    | "batch_status_change"
    | "price_tick"
    | "ai_metrics_tick";
  payload: Record<string, unknown>;
  /** UUID4 injected by the server for client-side deduplication (T297). */
  event_id?: string;
}

export interface ListResponse<T> {
  items: T[];
  limit: number;
  offset: number;
}

export interface SyntheticCustomerNotice {
  status_code: string;
  message: string;
}

export interface MarketReadinessCheck {
  check_code: string;
  status_code: string;
  observed_count?: number;
  required_count?: number;
  message?: string;
  source_code?: string | null;
  source_as_of?: string | null;
  freshness_status_code?: string | null;
  quality_status_code?: string | null;
}

export interface ProviderMode {
  profile: string;
  strict_external: boolean;
  required_provider_codes: string[];
  status_code: string;
  problem_count?: number;
  message: string;
}

export interface DomesticTop200Coverage {
  universe_code: "DOMESTIC_TOP200_MARKET_CAP";
  as_of_date?: string | null;
  resolved_trading_date?: string | null;
  selected_count: number;
  required_count: number;
  lookback_days: number;
  required_coverage_ratio?: number;
  expected_trading_days_by_market?: Record<string, number>;
  expected_member_days: number;
  observed_member_days: number;
  covered_tickers?: number;
  coverage_ratio: number;
  missing_member_days: number;
  latest_source_as_of?: string | null;
  source_code?: string | null;
  source_policy_code?: string | null;
  status_code: string;
  required?: boolean;
  snapshot_count?: number;
  blocking_reasons?: string[];
  message?: string;
}

export interface DomesticMarketStatus {
  status_code: string;
  source_code?: string | null;
  source_policy_code?: string | null;
  source_policy_label?: string | null;
  source_as_of?: string | null;
  freshness_status_code?: string | null;
  quality_status_code?: string | null;
  top200_coverage?: DomesticTop200Coverage;
  message?: string;
  checks?: MarketReadinessCheck[];
}

export interface ValuationSource {
  status_code: string;
  source_code?: string | null;
  source_as_of?: string | null;
  synthetic_as_of?: string | null;
  freshness_status_code?: string | null;
  quality_status_code?: string | null;
  message?: string;
}
