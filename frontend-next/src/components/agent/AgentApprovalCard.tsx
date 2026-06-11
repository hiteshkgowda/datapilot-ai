"use client";

import { motion } from "framer-motion";
import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  ShieldAlert,
  XCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { formatNumber } from "@/lib/format";
import type { PendingApproval } from "@/lib/api/types";

const OPERATION_LABELS: Record<string, string> = {
  create: "Create",
  update: "Update",
  delete: "Delete",
  bulk_update: "Bulk Update",
  soft_delete: "Soft Delete",
};

const DESTRUCTIVE_OPS = new Set(["delete", "bulk_update", "soft_delete"]);

interface AgentApprovalCardProps {
  approval: PendingApproval;
  isResuming: boolean;
  onApprove: () => void;
  onReject: () => void;
}

export function AgentApprovalCard({
  approval,
  isResuming,
  onApprove,
  onReject,
}: AgentApprovalCardProps) {
  const preview = approval.preview as Record<string, unknown>;

  const affectedRows = (preview.affected_row_count as number) ?? 0;
  const warnings = (preview.warnings as string[]) ?? [];
  const rollbackSupported = (preview.rollback_supported as boolean) ?? false;
  const plan = preview.plan as Record<string, unknown> | undefined;
  const operation = (plan?.operation as string) ?? "update";
  const tableName = (plan?.table_name as string) ?? "unknown";
  const rowPreview = preview.preview as
    | { columns: string[]; rows: Record<string, unknown>[]; total_count: number }
    | undefined;

  const isDestructive = DESTRUCTIVE_OPS.has(operation);
  const opLabel = OPERATION_LABELS[operation] ?? operation;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      className={cn(
        "rounded-xl border overflow-hidden",
        isDestructive ? "border-destructive/30" : "border-warning/30"
      )}
      role="alert"
      aria-live="assertive"
    >
      {/* Pulsing top accent bar */}
      <motion.div
        className={cn(
          "h-0.5 w-full",
          isDestructive ? "bg-destructive" : "bg-warning"
        )}
        animate={{ opacity: [0.5, 1, 0.5] }}
        transition={{ duration: 2, repeat: Infinity }}
        aria-hidden="true"
      />

      {/* Header */}
      <div
        className={cn(
          "flex items-center justify-between px-4 py-3 border-b",
          isDestructive
            ? "border-destructive/20 bg-destructive/[0.04]"
            : "border-warning/20 bg-warning/[0.04]"
        )}
      >
        <div className="flex items-center gap-2.5">
          <ShieldAlert
            className={cn(
              "h-4 w-4 shrink-0",
              isDestructive ? "text-destructive" : "text-warning"
            )}
            aria-hidden="true"
          />
          <div>
            <p className="text-sm font-semibold text-foreground">
              Approval required
            </p>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              Step {approval.step_index + 1} · {approval.step_label}
            </p>
          </div>
        </div>
        <Badge variant={isDestructive ? "destructive" : "warning"}>
          {opLabel}
        </Badge>
      </div>

      {/* Body */}
      <div
        className={cn(
          "p-4 space-y-4",
          isDestructive ? "bg-destructive/[0.02]" : "bg-warning/[0.02]"
        )}
      >
        {/* Stat grid */}
        <div className="grid grid-cols-3 gap-2 text-xs">
          <div className="rounded-lg bg-background/60 border border-border/40 px-3 py-2.5">
            <p className="text-muted-foreground/60 mb-1">Affected rows</p>
            <p
              className={cn(
                "text-xl font-bold tabular-nums leading-none",
                isDestructive ? "text-destructive" : "text-foreground"
              )}
            >
              {formatNumber(affectedRows)}
            </p>
          </div>
          <div className="rounded-lg bg-background/60 border border-border/40 px-3 py-2.5">
            <p className="text-muted-foreground/60 mb-1">Table</p>
            <p className="font-mono font-semibold text-foreground truncate text-sm">
              {tableName}
            </p>
          </div>
          <div className="rounded-lg bg-background/60 border border-border/40 px-3 py-2.5">
            <p className="text-muted-foreground/60 mb-1">Rollback</p>
            <p
              className={cn(
                "font-semibold text-sm",
                rollbackSupported
                  ? "text-[hsl(var(--success))]"
                  : "text-muted-foreground"
              )}
            >
              {rollbackSupported ? "Supported" : "None"}
            </p>
          </div>
        </div>

        {/* Warnings */}
        {warnings.length > 0 && (
          <div className="rounded-lg border border-warning/30 bg-warning/10 px-3 py-2.5 space-y-1">
            <div className="flex items-center gap-1.5 text-[11px] font-medium text-warning">
              <AlertTriangle className="h-3 w-3 shrink-0" aria-hidden="true" />
              {warnings.length === 1 ? "Warning" : `${warnings.length} warnings`}
            </div>
            {warnings.map((w, i) => (
              <p key={i} className="text-[11px] text-muted-foreground pl-4">
                {w}
              </p>
            ))}
          </div>
        )}

        {/* Preview rows */}
        {rowPreview && rowPreview.rows.length > 0 && (
          <div className="space-y-1.5">
            <p className="text-[10px] font-medium text-muted-foreground/60 uppercase tracking-wide">
              Preview — {Math.min(rowPreview.rows.length, 5)} of{" "}
              {formatNumber(rowPreview.total_count)} rows
            </p>
            <div className="overflow-x-auto rounded-lg border border-border/40">
              <table className="w-full text-xs" aria-label="Affected rows preview">
                <thead>
                  <tr className="border-b border-border/40 bg-muted/20">
                    {rowPreview.columns.slice(0, 5).map((col) => (
                      <th
                        key={col}
                        scope="col"
                        className="px-2.5 py-1.5 text-left text-[11px] font-semibold text-muted-foreground uppercase tracking-wide whitespace-nowrap"
                      >
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rowPreview.rows.slice(0, 5).map((row, i) => (
                    <tr
                      key={i}
                      className="border-b border-border/20 last:border-0 hover:bg-muted/10 transition-colors"
                    >
                      {rowPreview.columns.slice(0, 5).map((col) => (
                        <td
                          key={col}
                          className="px-2.5 py-1.5 font-mono text-foreground/80 truncate max-w-[100px]"
                        >
                          {row[col] === null ? (
                            <span className="italic text-muted-foreground/40">
                              null
                            </span>
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

        {/* Action buttons */}
        <div className="flex items-center gap-3 pt-1 border-t border-border/30">
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5"
            onClick={onReject}
            disabled={isResuming}
          >
            <XCircle className="h-3.5 w-3.5" aria-hidden="true" />
            Reject
          </Button>

          <Button
            variant={isDestructive ? "destructive" : "default"}
            size="sm"
            className="gap-1.5 min-w-[140px]"
            onClick={onApprove}
            disabled={isResuming}
          >
            {isResuming ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                Executing…
              </>
            ) : (
              <>
                <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
                Approve &amp; Execute
              </>
            )}
          </Button>

          <p className="text-[10px] text-muted-foreground/50 ml-auto">
            Will {opLabel.toLowerCase()} {formatNumber(affectedRows)} row
            {affectedRows !== 1 ? "s" : ""}
          </p>
        </div>
      </div>
    </motion.div>
  );
}
