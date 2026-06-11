"use client";

import { useEffect } from "react";
import { motion } from "framer-motion";
import type { Variants } from "framer-motion";
import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  ShieldAlert,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { formatNumber } from "@/lib/format";
import type { CrudPreviewResponse } from "@/lib/api/types";

const OPERATION_LABELS: Record<string, string> = {
  create: "Create",
  update: "Update",
  delete: "Delete",
  bulk_update: "Bulk Update",
  soft_delete: "Soft Delete",
};

const DESTRUCTIVE_OPS = new Set(["delete", "bulk_update", "soft_delete"]);

const backdropVariants: Variants = {
  hidden: { opacity: 0 },
  show: { opacity: 1 },
};

const panelVariants: Variants = {
  hidden: { opacity: 0, scale: 0.95, y: 8 },
  show: { opacity: 1, scale: 1, y: 0, transition: { duration: 0.2 } },
  exit: { opacity: 0, scale: 0.95, y: 8, transition: { duration: 0.15 } },
};

interface CrudApprovalModalProps {
  preview: CrudPreviewResponse;
  isExecuting: boolean;
  onApprove: () => void;
  onReject: () => void;
}

export function CrudApprovalModal({
  preview,
  isExecuting,
  onApprove,
  onReject,
}: CrudApprovalModalProps) {
  const { plan, affected_row_count, warnings, rollback_supported, preview: rowPreview } = preview;
  const isDestructive = DESTRUCTIVE_OPS.has(plan.operation);
  const opLabel = OPERATION_LABELS[plan.operation] ?? plan.operation;

  // Close on Escape
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !isExecuting) onReject();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isExecuting, onReject]);

  // Trap scroll
  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = ""; };
  }, []);

  return (
    <motion.div
      variants={backdropVariants}
      initial="hidden"
      animate="show"
      exit="hidden"
      transition={{ duration: 0.15 }}
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: "rgba(0,0,0,0.6)", backdropFilter: "blur(4px)" }}
      onClick={(e) => {
        if (e.target === e.currentTarget && !isExecuting) onReject();
      }}
      aria-modal="true"
      role="dialog"
      aria-labelledby="approval-title"
    >
      <motion.div
        variants={panelVariants}
        initial="hidden"
        animate="show"
        exit="exit"
        className={cn(
          "relative w-full max-w-lg rounded-2xl border bg-card shadow-2xl",
          isDestructive ? "border-destructive/30" : "border-border"
        )}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Close button */}
        <button
          onClick={onReject}
          disabled={isExecuting}
          className={cn(
            "absolute right-4 top-4 rounded-md p-1",
            "text-muted-foreground hover:text-foreground hover:bg-accent",
            "transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            "disabled:pointer-events-none disabled:opacity-50"
          )}
          aria-label="Close"
        >
          <X className="h-4 w-4" />
        </button>

        {/* Header */}
        <div className={cn(
          "flex items-start gap-4 p-6 pb-0",
        )}>
          <div className={cn(
            "flex h-10 w-10 shrink-0 items-center justify-center rounded-full",
            isDestructive ? "bg-destructive/10" : "bg-primary/10"
          )}>
            <ShieldAlert className={cn(
              "h-5 w-5",
              isDestructive ? "text-destructive" : "text-primary"
            )} />
          </div>
          <div>
            <h2 id="approval-title" className="text-base font-semibold text-foreground">
              Confirm {opLabel} Operation
            </h2>
            <p className="mt-0.5 text-sm text-muted-foreground">
              This operation will affect{" "}
              <span className="font-semibold text-foreground">
                {formatNumber(affected_row_count)} row{affected_row_count !== 1 ? "s" : ""}
              </span>{" "}
              in{" "}
              <span className="font-mono text-xs bg-muted px-1.5 py-0.5 rounded">
                {plan.schema_name ? `${plan.schema_name}.` : ""}{plan.table_name}
              </span>
            </p>
          </div>
        </div>

        {/* Body */}
        <div className="p-6 space-y-4">
          {/* Warnings */}
          {warnings.length > 0 && (
            <div className="rounded-lg border border-warning/30 bg-warning/5 p-3 space-y-1.5">
              <div className="flex items-center gap-1.5 text-xs font-medium text-warning">
                <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
                {warnings.length === 1 ? "Warning" : `${warnings.length} warnings`}
              </div>
              {warnings.map((w, i) => (
                <p key={i} className="text-xs text-muted-foreground pl-5">{w}</p>
              ))}
            </div>
          )}

          {/* Operation summary */}
          <div className="rounded-lg border border-border/50 bg-muted/30 p-4 space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">Operation</span>
              <Badge variant={isDestructive ? "destructive" : "default"} className="text-[11px]">
                {opLabel}
              </Badge>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">Affected rows</span>
              <span className="font-semibold tabular-nums text-foreground">
                {formatNumber(affected_row_count)}
              </span>
            </div>
            {plan.filters && plan.filters.length > 0 && (
              <div className="flex items-start justify-between text-xs gap-4">
                <span className="text-muted-foreground shrink-0">Filters</span>
                <span className="text-foreground text-right font-mono text-[11px]">
                  {plan.filters.map((f) => `${f.column} ${f.operator} ${String(f.value)}`).join(", ")}
                </span>
              </div>
            )}
            {plan.set_values && Object.keys(plan.set_values).length > 0 && (
              <div className="flex items-start justify-between text-xs gap-4">
                <span className="text-muted-foreground shrink-0">Set values</span>
                <span className="text-foreground text-right font-mono text-[11px]">
                  {Object.entries(plan.set_values)
                    .map(([k, v]) => `${k} = ${String(v)}`)
                    .join(", ")}
                </span>
              </div>
            )}
            <div className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">Rollback</span>
              <span className={cn(
                "text-[11px] font-medium",
                rollback_supported ? "text-[hsl(var(--success))]" : "text-muted-foreground"
              )}>
                {rollback_supported ? "Supported" : "Not supported"}
              </span>
            </div>
          </div>

          {/* Preview rows sample */}
          {rowPreview.rows.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wide">
                Affected rows preview ({Math.min(rowPreview.rows.length, 3)} of {formatNumber(rowPreview.total_count)})
              </p>
              <div className="overflow-x-auto rounded-lg border border-border/50">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-border/50 bg-muted/30">
                      {rowPreview.columns.slice(0, 5).map((col) => (
                        <th key={col} className="px-3 py-2 text-left font-medium text-muted-foreground">
                          {col}
                        </th>
                      ))}
                      {rowPreview.columns.length > 5 && (
                        <th className="px-3 py-2 text-left font-medium text-muted-foreground">
                          +{rowPreview.columns.length - 5} more
                        </th>
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {rowPreview.rows.slice(0, 3).map((row, i) => (
                      <tr key={i} className={cn(
                        "border-b border-border/30 last:border-0",
                        isDestructive ? "bg-destructive/3" : ""
                      )}>
                        {rowPreview.columns.slice(0, 5).map((col) => (
                          <td key={col} className="px-3 py-2 text-foreground/80 font-mono truncate max-w-[120px]">
                            {row[col] === null ? (
                              <span className="text-muted-foreground/40 italic">null</span>
                            ) : (
                              String(row[col])
                            )}
                          </td>
                        ))}
                        {rowPreview.columns.length > 5 && (
                          <td className="px-3 py-2 text-muted-foreground/40">…</td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        {/* Footer actions */}
        <div className="flex items-center justify-end gap-3 border-t border-border/50 px-6 py-4">
          <Button
            variant="outline"
            size="sm"
            onClick={onReject}
            disabled={isExecuting}
            className="min-w-[80px]"
          >
            Reject
          </Button>
          <Button
            variant={isDestructive ? "destructive" : "default"}
            size="sm"
            onClick={onApprove}
            disabled={isExecuting}
            className="min-w-[120px]"
          >
            {isExecuting ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Executing…
              </>
            ) : (
              <>
                <CheckCircle2 className="h-3.5 w-3.5" />
                Approve & Execute
              </>
            )}
          </Button>
        </div>
      </motion.div>
    </motion.div>
  );
}
