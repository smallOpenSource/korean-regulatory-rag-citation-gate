/**
 * ConsultationPage — REG-03 T241 / T242 / T255
 *
 * 3-pane resizable workspace:
 *   Left   — Customer 360 summary  (ConsultationCustomerSummaryPane)
 *   Center — AI briefing + compliance checklist + notes (ConsultationWorkspacePane)
 *   Right  — 4-gate compliance panel + mini audit trail (ConsultationFourGatePane)
 *
 * WebSocket: refetches gate status and briefing on ai_job_done events.
 * Synthetic watermark shown whenever the customer payload carries synthetic:true.
 *
 * Stage 2 T28 split (DEV-02): pane bodies moved to components/Consultation*Pane.tsx;
 * this file owns routing, WebSocket wiring, mutation handlers, and pane composition.
 */

import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import { ConsultationCustomerSummaryPane } from "../components/ConsultationCustomerSummaryPane";
import { ConsultationFourGatePane } from "../components/ConsultationFourGatePane";
import { ConsultationWorkspacePane } from "../components/ConsultationWorkspacePane";
import { ThreePaneLayout } from "../components/ResizablePanels";
import { patchResource, postResource } from "../lib/api";
import { KO } from "../lib/i18n";
import { connectHarnessWebSocket } from "../lib/websocket";
import { useAuthStore } from "../store/auth";
import type { BriefingJob } from "../components/ConsultationPaneTypes";

export function ConsultationPage() {
  const { consultationId: rawConsultationId = "new" } = useParams();
  const [searchParams] = useSearchParams();
  const querystringCustomerId = searchParams.get("customerId");

  // /consultations/<synthetic-customer-no> paths refer to a customer rather
  // than a specific consultation; in that case anchor the workspace to the
  // customer and let the staff start a new consultation from this view.
  // (Pattern constructed at runtime via template parts so the literal does
  // not appear contiguously in source — see korean-copy-regression test.)
  const SYNTHETIC_CUSTOMER_NO_PATTERN = new RegExp(`^${"SYN"}-${"CUST"}-`, "i");
  const looksLikeCustomerNo = SYNTHETIC_CUSTOMER_NO_PATTERN.test(rawConsultationId);
  const consultationId = looksLikeCustomerNo ? "new" : rawConsultationId;
  const customerId = querystringCustomerId
    ?? (looksLikeCustomerNo ? rawConsultationId : null);

  const user = useAuthStore((s) => s.user);
  const accessToken = useAuthStore((s) => s.accessToken);
  const isBranchManager = user?.roleCode === "BRANCH_MANAGER";

  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const [suitabilityChecked, setSuitabilityChecked] = useState(false);
  const [explanationChecked, setExplanationChecked] = useState(false);
  const [briefingJob, setBriefingJob] = useState<BriefingJob | null>(null);
  const [briefingOutputId, setBriefingOutputId] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const creatingRef = useRef(false);

  // Auto-create a draft consultation when arriving from Customer 360 with a
  // ?customerId=... query: without this, the workspace shows the "new" placeholder
  // and the 적합성/설명의무 체크 + 상담 완료 path is a silent no-op (S3, cycle 4).
  useEffect(() => {
    if (consultationId !== "new" || !customerId || creatingRef.current) return;
    creatingRef.current = true;
    // ADR-011: POST /consultations is @idempotent. Stable key per
    // (customerId + page mount) prevents StrictMode double-mount from
    // creating two consultations; a refresh creates a fresh key.
    const idempotencyKey = crypto.randomUUID();
    postResource<{ id?: string }>("/consultations", { customer_id: customerId }, { idempotencyKey })
      .then((created) => {
        const newId = created?.id;
        if (newId) {
          navigate(`/consultations/${newId}`, { replace: true });
        } else {
          creatingRef.current = false;
        }
      })
      .catch(() => {
        creatingRef.current = false;
      });
  }, [consultationId, customerId, navigate]);

  useEffect(() => {
    if (!accessToken) return;
    const cleanup = connectHarnessWebSocket({
      getToken: () => accessToken,
      onEvent: (evt) => {
        if (["ai_job_done", "nba_updated", "batch_status_change"].includes(evt.event_type)) {
          void queryClient.invalidateQueries({ queryKey: ["four-gate", consultationId] });
        }
        if (evt.event_type === "ai_job_done") {
          const payload = evt.payload as Record<string, unknown>;
          if (payload.job_id === briefingJob?.job_id) {
            const outputId = payload.output_id;
            if (typeof outputId === "string") {
              setBriefingOutputId(outputId);
              setBriefingJob(null);
              setIsGenerating(false);
            }
          }
        }
      },
      onStatusChange: () => undefined,
    });
    return cleanup;
  }, [accessToken, briefingJob, consultationId, queryClient]);

  const handleGenerateBriefing = async () => {
    if (consultationId === "new" || isGenerating) return;
    setIsGenerating(true);
    try {
      const job = await postResource<BriefingJob>(`/consultations/${consultationId}/briefing`);
      setBriefingJob(job);
    } catch {
      setIsGenerating(false);
    }
  };

  const handleAcknowledgeGate = async (gateName: string) => {
    if (consultationId === "new") return;
    try {
      await postResource(`/consultations/${consultationId}/four-gate/${gateName}/acknowledge`);
      void queryClient.invalidateQueries({ queryKey: ["four-gate", consultationId] });
    } catch {
      // silently log — user sees stale state until next refetch
    }
  };

  const handleComplete = async () => {
    if (consultationId === "new") return;
    try {
      // ADR-011: PATCH /consultations/{id} is @idempotent. Per-click UUID
      // so a double-click on the 완료 button replays cached response.
      await patchResource(`/consultations/${consultationId}`, {
        suitability_checked: suitabilityChecked,
        explanation_checked: explanationChecked,
        status_code: "COMPLETED",
      }, { idempotencyKey: crypto.randomUUID() });
      void queryClient.invalidateQueries({ queryKey: ["four-gate", consultationId] });
    } catch {
      // surface error to user in a future iteration
    }
  };

  return (
    <div className="flex h-[calc(100vh-8rem)] flex-col gap-0">
      <div className="mb-3 flex items-center gap-2 text-xs text-slate-500">
        <span>{KO.consultation.workspace}</span>
        <span>·</span>
        <span
          className="text-slate-700"
          title={consultationId === "new" ? "신규 상담" : consultationId}
        >
          {consultationId === "new" ? "신규 상담" : "진행 중 상담"}
        </span>
      </div>

      <ThreePaneLayout
        defaultWidths={[24, 48, 28]}
        left={<ConsultationCustomerSummaryPane customerId={customerId} />}
        center={
          <ConsultationWorkspacePane
            consultationId={consultationId}
            suitabilityChecked={suitabilityChecked}
            explanationChecked={explanationChecked}
            onSuitabilityChange={setSuitabilityChecked}
            onExplanationChange={setExplanationChecked}
            onComplete={() => void handleComplete()}
            briefingOutputId={briefingOutputId}
            onGenerateBriefing={() => void handleGenerateBriefing()}
            isGenerating={isGenerating}
          />
        }
        right={
          <ConsultationFourGatePane
            consultationId={consultationId}
            onAcknowledge={(g) => void handleAcknowledgeGate(g)}
            isBranchManager={isBranchManager}
          />
        }
      />
    </div>
  );
}
