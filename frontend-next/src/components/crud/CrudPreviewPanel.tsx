"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { Variants } from "framer-motion";
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardCopy,
  Clock,
  Loader2,
  RotateCcw,
  ShieldCheck,
  TableProperties,
  Undo2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { formatNumber } from "@/lib/format";
import { useCrudRollback } from "@/hooks/use-crud";
import { CrudAuditViewer } from "./CrudAuditViewer";
import type {
  CrudExecuteResponse,
  CrudPreviewResponse,
} from "@/lib/api/types";

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

const OPERATION_LABELS: Record<string, string> = {
  create: "Create",
  update: "Update",
  delete: "Delete",
  bulk_update: "Bulk Update",
  soft_delete: "Soft Delete",
};

const DESTRUCTIVE_OPS = new Set(["delete", "bulk_update", "soft_delete"]);

type Tab = "operation" | "rollback" | "audit";

const fadeUp: Variants = {
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0, transition: { duration: 0.25 } },
  exit: { opacity: 0, y: -6, transition: { duration: 0.15 } },
};

// ---------------------------------------------------------------------------
// Tab bar
// ---------------------------------------------------------------------------

const TABS: { id: Tab; label: string }[] = [
  { id: "operation", label: "Operation" },
  { id: "rollback", label: "Rollback" },
  { id: "audit", label: "Audit log" },
];

function TabBar({
  active,
  onChange,
}: {
  active: Tab;
  onChange: (t: Tab) => void;
}) {
  return (
    <div className="flex items-center gap-1 border-b border-border/50 pb-0">
      {TABS.map((t) => (
        <button
          key={t.id}
          onClick={() => onChange(t.id)}
          className={cn(
            "relative px-4 py-2.5 text-sm font-medium transition-colors",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-t-md",
            active === t.id
              ? "text-primary"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          {t.label}
          {active === t.id && (
            <motion.span
              layoutId="crud-tab-indicator"
              className="absolute inset-x-0 -bottom-px h-0.5 bg-primary rounded-full"
              transition={{ type: "spring", stiffness: 400, damping: 35 }}
            />
          )}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Preview skeleton
// ---------------------------------------------------------------------------

function PreviewSkeleton() {
  return (
    <div className="space-y-4 animate-pulse">
      <div className="rounded-xl border border-border/30 bg-card/40 p-5 space-y-4">
        <div className="flex items-center justify-between">
          <Skeleton className="h-5 w-32" />
          <Skeleton className="h-5 w-20 rounded-full" />
        </div>
        <div className="grid grid-cols-3 gap-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="rounded-lg border border-border/30 bg-muted/20 px-4 py-3 space-y-1.5">
              <Skeleton className="h-3 w-12" />
              <Skeleton className="h-5 w-8" />
            </div>
          ))}
        </div>
        <Skeleton className="h-32 w-full rounded-lg" />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Preview result display
// ---------------------------------------------------------------------------

function PreviewResult({
  result,
  onApprove,
}: {
  result: CrudPreviewResponse;
  onApprove: () => void;
}) {
  const { plan, affected_row_count, warnings, rollback_supported, preview } = result;
  const isDestructive = DESTRUCTIVE_OPS.has(plan.operation);
  const opLabel = OPERATION_LABELS[plan.operation] ?? plan.operation;

  return (
    <motion.div variants={fadeUp} initial="hidden" animate="show" className="space-y-4">
      {/* Summary card */}
      <div className={cn(
        "rounded-xl border bg-card/60 p-5 space-y-4",
        isDestructive ? "border-destructive/30" : "border-border/50"
      )}>
        {/* Header */}
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-foreground">Operation preview</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              Review before approving
            </p>
          </div>
          <Badge variant={isDestructive ? "destructive" : "default"}>
            {opLabel}
          </Badge>
        </div>

        {/* Metric row */}
        <div className="grid grid-cols-3 gap-3">
          <div className="rounded-lg border border-border/40 bg-muted/20 px-4 py-3">
            <p className="text-[10px] text-muted-foreground uppercase tracking-wide mb-1">
              Affected rows
            </p>
            <p className={cn(
              "text-xl font-bold tabular-nums",
              isDestructive ? "text-destructive" : "text-foreground"
            )}>
              {formatNumber(affected_row_count)}
            </p>
          </div>
          <div className="rounded-lg border border-border/40 bg-muted/20 px-4 py-3">
            <p className="text-[10px] text-muted-foreground uppercase tracking-wide mb-1">
              Table
            </p>
            <p className="text-sm font-semibold text-foreground font-mono truncate">
              {plan.table_name}
            </p>
          </div>
          <div className="rounded-lg border border-border/40 bg-muted/20 px-4 py-3">
            <p className="text-[10px] text-muted-foreground uppercase tracking-wide mb-1">
              Rollback
            </p>
            <p className={cn(
              "text-sm font-semibold",
              rollback_supported ? "text-[hsl(var(--success))]" : "text-muted-foreground"
            )}>
              {rollback_supported ? "Supported" : "Not available"}
            </p>
          </div>
        </div>

        {/* Warnings */}
        {warnings.length > 0 && (
          <div className="rounded-lg border border-warning/30 bg-warning/5 p-3 space-y-1">
            <div className="flex items-center gap-1.5 text-xs font-medium text-warning">
              <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
              {warnings.length === 1 ? "Warning" : `${warnings.length} warnings`}
            </div>
            {warnings.map((w, i) => (
              <p key={i} className="text-xs text-muted-foreground pl-5">{w}</p>
            ))}
          </div>
        )}

        {/* Filters / set values summary */}
        {(plan.filters?.length || plan.set_values) && (
          <div className="rounded-lg border border-border/40 bg-muted/10 px-4 py-3 space-y-2">
            {plan.filters && plan.filters.length > 0 && (
              <div className="flex items-start gap-3 text-xs">
                <span className="text-muted-foreground shrink-0 w-14">WHERE</span>
                <span className="font-mono text-foreground/80">
                  {plan.filters.map(
                    (f) => `${f.column} ${f.operator} ${String(f.value)}`
                  ).join(" AND ")}
                </span>
              </div>
            )}
            {plan.set_values && Object.keys(plan.set_values).length > 0 && (
              <div className="flex items-start gap-3 text-xs">
                <span className="text-muted-foreground shrink-0 w-14">SET</span>
                <span className="font-mono text-foreground/80">
                  {Object.entries(plan.set_values)
                    .map(([k, v]) => `${k} = ${String(v)}`)
                    .join(", ")}
                </span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Preview rows table */}
      {preview.rows.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-medium text-muted-foreground flex items-center gap-1.5">
            <TableProperties className="h-3.5 w-3.5" />
            Preview rows ({Math.min(preview.rows.length, 10)} of {formatNumber(preview.total_count)})
          </p>
          <div className="overflow-x-auto rounded-xl border border-border/50 bg-card/40">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border/50 bg-muted/20">
                  {preview.columns.map((col) => (
                    <th
                      key={col}
                      className="px-3 py-2.5 text-left font-medium text-muted-foreground whitespace-nowrap"
                    >
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {preview.rows.slice(0, 10).map((row, i) => (
                  <tr
                    key={i}
                    className="border-b border-border/20 last:border-0 hover:bg-accent/20 transition-colors"
                  >
                    {preview.columns.map((col) => (
                      <td
                        key={col}
                        className="px-3 py-2 font-mono text-foreground/80 max-w-[150px] truncate"
                      >
                        {row[col] === null ? (
                          <span className="italic text-muted-foreground/40">null</span>
                        ) : (
                          String(row[col])
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Approve CTA */}
      <div className="flex items-center justify-between rounded-xl border border-border/50 bg-card/40 px-5 py-4">
        <p className="text-sm text-muted-foreground">
          Looks correct?{" "}
          <span className="text-foreground font-medium">Approve to execute.</span>
        </p>
        <Button
          variant={isDestructive ? "destructive" : "default"}
          onClick={onApprove}
          className="gap-1.5 shrink-0"
        >
          <ShieldCheck className="h-4 w-4" />
          Review & Approve
        </Button>
      </div>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Execute result display
// ---------------------------------------------------------------------------

function ExecuteResult({
  result,
  onReset,
}: {
  result: CrudExecuteResponse;
  onReset: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const opLabel = OPERATION_LABELS[result.operation] ?? result.operation;

  function copyToken() {
    if (!result.rollback_token) return;
    navigator.clipboard.writeText(result.rollback_token).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <motion.div variants={fadeUp} initial="hidden" animate="show" className="space-y-4">
      {/* Success banner */}
      <div className="flex items-center gap-3 rounded-xl border border-[hsl(var(--success)/0.3)] bg-[hsl(var(--success)/0.05)] px-5 py-4">
        <CheckCircle2 className="h-5 w-5 text-[hsl(var(--success))] shrink-0" />
        <div>
          <p className="text-sm font-semibold text-foreground">
            {opLabel} completed successfully
          </p>
          <p className="text-xs text-muted-foreground">
            {formatNumber(result.affected_rows)} row{result.affected_rows !== 1 ? "s" : ""} affected
            on{" "}
            <span className="font-mono">{result.table_name}</span>
          </p>
        </div>
      </div>

      {/* Detail grid */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <div className="rounded-xl border border-border/40 bg-card/40 px-4 py-3">
          <p className="text-[10px] text-muted-foreground uppercase tracking-wide mb-1">Operation</p>
          <Badge variant="default" className="text-[11px]">{opLabel}</Badge>
        </div>
        <div className="rounded-xl border border-border/40 bg-card/40 px-4 py-3">
          <p className="text-[10px] text-muted-foreground uppercase tracking-wide mb-1">Rows affected</p>
          <p className="text-xl font-bold tabular-nums text-foreground">{formatNumber(result.affected_rows)}</p>
        </div>
        <div className="rounded-xl border border-border/40 bg-card/40 px-4 py-3">
          <p className="text-[10px] text-muted-foreground uppercase tracking-wide mb-1 flex items-center gap-1">
            <Clock className="h-3 w-3" />Duration
          </p>
          <p className="text-sm font-semibold text-foreground tabular-nums">
            {result.execution_time_ms.toFixed(1)} ms
          </p>
        </div>
      </div>

      {/* Rollback token */}
      {result.rollback_token && (
        <div className="rounded-xl border border-border/50 bg-card/40 p-4 space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium text-muted-foreground flex items-center gap-1.5">
              <Undo2 className="h-3.5 w-3.5" />
              Rollback token
            </p>
            <Button
              variant="ghost"
              size="sm"
              className="h-6 gap-1 text-[11px] text-muted-foreground hover:text-foreground"
              onClick={copyToken}
            >
              <ClipboardCopy className="h-3 w-3" />
              {copied ? "Copied!" : "Copy"}
            </Button>
          </div>
          <p className="font-mono text-[11px] text-foreground/70 break-all bg-muted/30 rounded p-2">
            {result.rollback_token}
          </p>
          <p className="text-[11px] text-muted-foreground">
            Save this token to roll back the operation within the next hour.
          </p>
        </div>
      )}

      {/* Audit ID */}
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>Audit ID: <span className="font-mono text-foreground/60">{result.audit_id}</span></span>
        <Button
          variant="ghost"
          size="sm"
          className="h-7 gap-1 text-xs text-muted-foreground hover:text-foreground"
          onClick={onReset}
        >
          <RotateCcw className="h-3 w-3" />
          New operation
        </Button>
      </div>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Rollback section (shown in rollback tab)
// ---------------------------------------------------------------------------

function RollbackSection({ connectionId }: { connectionId: string | null }) {
  const [token, setToken] = useState("");
  const [connId, setConnId] = useState(connectionId ?? "");
  const { mutate, isPending, data, reset } = useCrudRollback();

  // Keep local connId in sync when parent changes
  if (connectionId && connId === "" ) {
    setConnId(connectionId);
  }

  function submit() {
    const t = token.trim();
    const c = connId.trim();
    if (!t || !c || isPending) return;
    mutate({ connection_id: c, rollback_token: t });
  }

  return (
    <div className="space-y-5">
      <div>
        <p className="text-sm font-semibold text-foreground">Rollback operation</p>
        <p className="text-xs text-muted-foreground mt-0.5">
          Enter a rollback token to restore the previous state.
        </p>
      </div>

      <div className="space-y-3">
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            Connection ID
          </label>
          <input
            type="text"
            value={connId}
            onChange={(e) => setConnId(e.target.value)}
            placeholder="connection ID"
            disabled={isPending}
            className={cn(
              "w-full rounded-lg border border-border/60 bg-card/60 px-3 py-2",
              "text-sm font-mono text-foreground placeholder:text-muted-foreground/50",
              "focus:outline-none focus:border-primary/50 transition-colors",
              "disabled:opacity-50"
            )}
          />
        </div>

        <div className="space-y-1.5">
          <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            Rollback token
          </label>
          <textarea
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="Paste the rollback token here…"
            disabled={isPending}
            rows={3}
            className={cn(
              "w-full resize-none rounded-lg border border-border/60 bg-card/60 px-3 py-2",
              "text-sm font-mono text-foreground placeholder:text-muted-foreground/50",
              "focus:outline-none focus:border-primary/50 transition-colors",
              "disabled:opacity-50"
            )}
          />
        </div>

        <Button
          onClick={submit}
          disabled={!token.trim() || !connId.trim() || isPending}
          variant="outline"
          className="w-full gap-1.5"
        >
          {isPending ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Rolling back…
            </>
          ) : (
            <>
              <Undo2 className="h-4 w-4" />
              Roll back operation
            </>
          )}
        </Button>
      </div>

      {/* Result */}
      <AnimatePresence>
        {data && (
          <motion.div
            variants={fadeUp}
            initial="hidden"
            animate="show"
            exit="exit"
            className="rounded-xl border border-[hsl(var(--success)/0.3)] bg-[hsl(var(--success)/0.05)] p-4 space-y-2"
          >
            <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <CheckCircle2 className="h-4 w-4 text-[hsl(var(--success))]" />
              Rollback complete
            </div>
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div>
                <span className="text-muted-foreground block">Rows restored</span>
                <span className="font-semibold tabular-nums text-foreground">
                  {formatNumber(data.restored_rows)}
                </span>
              </div>
              <div>
                <span className="text-muted-foreground block">Duration</span>
                <span className="font-semibold tabular-nums text-foreground">
                  {data.execution_time_ms.toFixed(1)} ms
                </span>
              </div>
            </div>
            <p className="text-[11px] text-muted-foreground">
              Audit ID: <span className="font-mono">{data.audit_id}</span>
            </p>
            <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={reset}>
              Clear
            </Button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ---------------------------------------------------------------------------
// CrudPreviewPanel — right panel with tabs
// ---------------------------------------------------------------------------

interface CrudPreviewPanelProps {
  activeTab: Tab;
  onTabChange: (t: Tab) => void;
  preview: CrudPreviewResponse | null;
  isPreviewing: boolean;
  executeResult: CrudExecuteResponse | null;
  onApprove: () => void;
  onReset: () => void;
  connectionId: string | null;
}

export function CrudPreviewPanel({
  activeTab,
  onTabChange,
  preview,
  isPreviewing,
  executeResult,
  onApprove,
  onReset,
  connectionId,
}: CrudPreviewPanelProps) {
  return (
    <div className="flex flex-col h-full space-y-4">
      <TabBar active={activeTab} onChange={onTabChange} />

      <div className="flex-1 overflow-y-auto">
        <AnimatePresence mode="wait">
          {/* ---- Operation tab ---- */}
          {activeTab === "operation" && (
            <motion.div
              key="operation"
              variants={fadeUp}
              initial="hidden"
              animate="show"
              exit="exit"
            >
              {isPreviewing && <PreviewSkeleton />}

              {!isPreviewing && !preview && !executeResult && (
                <div className="flex flex-col items-center justify-center py-24 text-center">
                  <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10 mb-4">
                    <ShieldCheck className="h-7 w-7 text-primary" aria-hidden="true" />
                  </div>
                  <p className="text-sm font-medium text-foreground">No operation yet</p>
                  <p className="mt-1 text-xs text-muted-foreground max-w-[260px]">
                    Describe your data change on the left and click Preview to see what will be affected.
                  </p>
                </div>
              )}

              {!isPreviewing && preview && !executeResult && (
                <PreviewResult result={preview} onApprove={onApprove} />
              )}

              {!isPreviewing && executeResult && (
                <ExecuteResult result={executeResult} onReset={onReset} />
              )}
            </motion.div>
          )}

          {/* ---- Rollback tab ---- */}
          {activeTab === "rollback" && (
            <motion.div
              key="rollback"
              variants={fadeUp}
              initial="hidden"
              animate="show"
              exit="exit"
            >
              <RollbackSection connectionId={connectionId} />
            </motion.div>
          )}

          {/* ---- Audit tab ---- */}
          {activeTab === "audit" && (
            <motion.div
              key="audit"
              variants={fadeUp}
              initial="hidden"
              animate="show"
              exit="exit"
            >
              <CrudAuditViewer connectionId={connectionId} />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
