import { useEffect } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { AftercarePage } from "./pages/AftercarePage";
import { AutopilotDemoPage } from "./pages/AutopilotDemoPage";
import { AIAdminDashboardPage } from "./pages/AIAdminDashboardPage";
import { AIModelCardsPage } from "./pages/AIModelCardsPage";
import { AIPolicyPage } from "./pages/AIPolicyPage";
import { AuditPage } from "./pages/AuditPage";
import { AuditViewerPage } from "./pages/AuditViewerPage";
import { BatchPage } from "./pages/BatchPage";
import { ConflictOfInterestPage } from "./pages/ConflictOfInterestPage";
import { ConsultationPage } from "./pages/ConsultationPage";
import { ConsentsPage } from "./pages/ConsentsPage";
import { KycEddPage } from "./pages/KycEddPage";
import { DataGovernancePage } from "./pages/DataGovernancePage";
import { MarketingReviewPage } from "./pages/MarketingReviewPage";
import { Customer360Page } from "./pages/Customer360Page";
import { CustomersPage } from "./pages/CustomersPage";
import { DashboardPage } from "./pages/DashboardPage";
import { DisputeCasePage } from "./pages/DisputeCasePage";
import { EmailDraftsPage } from "./pages/EmailDraftsPage";
import { ForbiddenPage } from "./pages/ForbiddenPage";
import { HouseViewDetailPage } from "./pages/HouseViewDetailPage";
import { HouseViewsPage } from "./pages/HouseViewsPage";
import { KoreanAIBasicActPage } from "./pages/KoreanAIBasicActPage";
import { LoginPage } from "./pages/LoginPage";
import { NbaPage } from "./pages/NbaPage";
import { QuarantineDashboard } from "./pages/QuarantineDashboard";
import { RagPage } from "./pages/RagPage";
import { RightsNoticePage } from "./pages/RightsNoticePage";
import { useAuthStore } from "./store/auth";

export function AuthSessionRestorer() {
  const restoreSession = useAuthStore((state) => state.restoreSession);
  const restoreAttempted = useAuthStore((state) => state.restoreAttempted);
  const accessToken = useAuthStore((state) => state.accessToken);
  const sessionRestoreFailed = useAuthStore((state) => state.sessionRestoreFailed);

  useEffect(() => {
    void restoreSession();
  }, [restoreSession]);

  // T3-2 (F14) DEV-only "page ready" signal — Playwright audit-e2e waits for
  // this flag after each page.goto to defeat the post-reload race between
  // restoreSession (async cookie-exchange) and ProtectedRoute's accessToken
  // check.
  //
  // Semantics (svc-viability-v2 cycle 근본 fix):
  //   restoreAttempted === true
  //   AND (accessToken !== null    // success path
  //        OR sessionRestoreFailed) // explicit failure path
  //
  // 이전 cycle (e2ec000 revert 이전) restoreAttempted 단독 조건은 failure
  // path가 cookie-exchange 완료 *직전*에도 일부 transient state에서 true로
  // 보여 ProtectedRoute가 accessToken=null 시점에 render → /login bounce를
  // 일으켰다. 두 path 모두 명시적으로 cover하여 ready 신호가 token actually
  // restored OR session restore failure 확정 시에만 fire되도록 한다.
  //
  // import.meta.env.DEV gate로 Vite tree-shake 시 production bundle에서
  // 제거 (window.__wmahAuth 패턴 동일).
  useEffect(() => {
    if (!import.meta.env.DEV) return;
    if (!restoreAttempted) return;
    if (accessToken !== null || sessionRestoreFailed) {
      (window as unknown as { __wmahPageReady?: boolean }).__wmahPageReady = true;
    }
  }, [restoreAttempted, accessToken, sessionRestoreFailed]);

  return null;
}

export function App() {
  return (
    <>
      <AuthSessionRestorer />
      <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/403" element={<ForbiddenPage />} />
      <Route element={<ProtectedRoute routeKey="dashboard"><Layout /></ProtectedRoute>}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/customers" element={<ProtectedRoute routeKey="customers"><CustomersPage /></ProtectedRoute>} />
        <Route path="/customers/:customerId" element={<ProtectedRoute routeKey="customer360"><Customer360Page /></ProtectedRoute>} />
        <Route path="/consultations/:consultationId" element={<ProtectedRoute routeKey="consultation"><ConsultationPage /></ProtectedRoute>} />
        <Route path="/nba" element={<ProtectedRoute routeKey="nba"><NbaPage /></ProtectedRoute>} />
        <Route path="/aftercare" element={<ProtectedRoute routeKey="aftercare"><AftercarePage /></ProtectedRoute>} />
        <Route path="/email-drafts" element={<ProtectedRoute routeKey="emailDrafts"><EmailDraftsPage /></ProtectedRoute>} />
        <Route path="/house-views" element={<ProtectedRoute routeKey="houseViews"><HouseViewsPage /></ProtectedRoute>} />
        <Route path="/house-views/:houseViewId" element={<ProtectedRoute routeKey="houseViews"><HouseViewDetailPage /></ProtectedRoute>} />
        <Route path="/house-views/:houseViewId/activate" element={<ProtectedRoute routeKey="houseViewActivation"><HouseViewDetailPage activation /></ProtectedRoute>} />
        <Route path="/rag" element={<ProtectedRoute routeKey="rag"><RagPage /></ProtectedRoute>} />
        <Route path="/batch" element={<ProtectedRoute routeKey="batch"><BatchPage /></ProtectedRoute>} />
        <Route path="/audit" element={<ProtectedRoute routeKey="audit"><AuditPage /></ProtectedRoute>} />
        <Route path="/quarantine" element={<ProtectedRoute routeKey="quarantine"><QuarantineDashboard /></ProtectedRoute>} />
        {/* Governance pages — Task #11 */}
        <Route path="/audit-viewer" element={<ProtectedRoute routeKey="auditViewer"><AuditViewerPage /></ProtectedRoute>} />
        <Route path="/rights-notice" element={<ProtectedRoute routeKey="rightsNotice"><RightsNoticePage /></ProtectedRoute>} />
        <Route path="/dispute-cases" element={<ProtectedRoute routeKey="disputeCase"><DisputeCasePage /></ProtectedRoute>} />
        <Route path="/conflict-of-interest" element={<ProtectedRoute routeKey="conflictOfInterest"><ConflictOfInterestPage /></ProtectedRoute>} />
        <Route path="/marketing-review" element={<ProtectedRoute routeKey="marketingReview"><MarketingReviewPage /></ProtectedRoute>} />
        <Route path="/data-governance" element={<ProtectedRoute routeKey="dataGovernance"><DataGovernancePage /></ProtectedRoute>} />
        <Route path="/consents" element={<ProtectedRoute routeKey="consents"><ConsentsPage /></ProtectedRoute>} />
        <Route path="/kyc-edd" element={<ProtectedRoute routeKey="kycEdd"><KycEddPage /></ProtectedRoute>} />
        {/* AI governance pages — Task #12 */}
        <Route path="/ai-model-cards" element={<ProtectedRoute routeKey="aiModelCards"><AIModelCardsPage /></ProtectedRoute>} />
        <Route path="/ai-policy" element={<ProtectedRoute routeKey="aiPolicy"><AIPolicyPage /></ProtectedRoute>} />
        <Route path="/korean-ai-act" element={<ProtectedRoute routeKey="koreanAIAct"><KoreanAIBasicActPage /></ProtectedRoute>} />
        <Route path="/ai-admin-dashboard" element={<ProtectedRoute routeKey="aiAdminDashboard"><AIAdminDashboardPage /></ProtectedRoute>} />
        <Route path="/autopilot-demo" element={<ProtectedRoute routeKey="autopilotDemo"><AutopilotDemoPage /></ProtectedRoute>} />
      </Route>
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </>
  );
}
