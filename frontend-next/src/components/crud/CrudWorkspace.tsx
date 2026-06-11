"use client";

import { useState } from "react";
import { AnimatePresence } from "framer-motion";
import { Skeleton } from "@/components/ui/skeleton";
import { useConnections } from "@/hooks/use-connections";
import { useCrudExecute, useCrudPreview } from "@/hooks/use-crud";
import { CrudApprovalModal } from "./CrudApprovalModal";
import { CrudPreviewPanel } from "./CrudPreviewPanel";
import { CrudRequestPanel } from "./CrudRequestPanel";
import type {
  CrudExecuteResponse,
  CrudPreviewResponse,
} from "@/lib/api/types";

type Tab = "operation" | "rollback" | "audit";

export function CrudWorkspace() {
  const { data: connectionsData, isLoading: connectionsLoading } = useConnections();
  const connections = connectionsData ?? [];

  // Connection selection — auto-select first connection when available
  const [connectionId, setConnectionId] = useState<string>("");
  const resolvedConnectionId = connectionId || connections[0]?.id || "";

  // Current request state
  const [lastQuestion, setLastQuestion] = useState("");
  const [preview, setPreview] = useState<CrudPreviewResponse | null>(null);
  const [executeResult, setExecuteResult] = useState<CrudExecuteResponse | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [activeTab, setActiveTab] = useState<Tab>("operation");

  // Mutations
  const previewMutation = useCrudPreview();
  const executeMutation = useCrudExecute();

  function handleSubmit(question: string) {
    setLastQuestion(question);
    setPreview(null);
    setExecuteResult(null);
    setActiveTab("operation");

    previewMutation.mutate(
      { connection_id: resolvedConnectionId, question },
      {
        onSuccess: (data) => {
          setPreview(data);
        },
      }
    );
  }

  function handleApprove() {
    if (!preview) return;
    setShowModal(false);
    executeMutation.mutate(
      {
        connection_id: preview.connection_id,
        plan: preview.plan,
        confirmation_token: preview.confirmation_token ?? undefined,
        question: lastQuestion,
      },
      {
        onSuccess: (data) => {
          setExecuteResult(data);
          setPreview(null);
        },
      }
    );
  }

  function handleReject() {
    setShowModal(false);
  }

  function handleReset() {
    setPreview(null);
    setExecuteResult(null);
    previewMutation.reset();
    executeMutation.reset();
  }

  return (
    <>
      <div className="flex h-full min-h-0">
        {/* ── Left panel ──────────────────────────────────────────────── */}
        <div className="w-80 xl:w-96 shrink-0 border-r border-border/50 overflow-y-auto p-6">
          {connectionsLoading ? (
            <div className="space-y-6">
              <div className="flex items-center gap-3">
                <Skeleton className="h-9 w-9 rounded-lg" />
                <div className="space-y-1.5">
                  <Skeleton className="h-4 w-36" />
                  <Skeleton className="h-3 w-48" />
                </div>
              </div>
              <div className="space-y-2">
                <Skeleton className="h-3 w-32" />
                <Skeleton className="h-9 w-full rounded-lg" />
              </div>
              <div className="space-y-2">
                <Skeleton className="h-3 w-16" />
                <Skeleton className="h-24 w-full rounded-xl" />
              </div>
            </div>
          ) : (
            <CrudRequestPanel
              connections={connections}
              connectionId={resolvedConnectionId}
              onConnectionChange={setConnectionId}
              onSubmit={handleSubmit}
              isPending={previewMutation.isPending}
            />
          )}
        </div>

        {/* ── Right panel ─────────────────────────────────────────────── */}
        <div className="flex-1 min-w-0 overflow-y-auto p-6">
          <CrudPreviewPanel
            activeTab={activeTab}
            onTabChange={setActiveTab}
            preview={preview}
            isPreviewing={previewMutation.isPending || executeMutation.isPending}
            executeResult={executeResult}
            onApprove={() => setShowModal(true)}
            onReset={handleReset}
            connectionId={resolvedConnectionId || null}
          />
        </div>
      </div>

      {/* ── Approval modal (portal-style fixed overlay) ─────────────── */}
      <AnimatePresence>
        {showModal && preview && (
          <CrudApprovalModal
            preview={preview}
            isExecuting={executeMutation.isPending}
            onApprove={handleApprove}
            onReject={handleReject}
          />
        )}
      </AnimatePresence>
    </>
  );
}
