"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { Variants } from "framer-motion";
import {
  ChevronDown,
  ChevronRight,
  Loader2,
  RefreshCw,
  Search,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { formatRelativeTime, formatNumber } from "@/lib/format";
import { useCrudAudit } from "@/hooks/use-crud";
import type { AuditEntry } from "@/lib/api/types";

const OPERATION_VARIANTS: Record<string, "destructive" | "warning" | "success" | "default"> = {
  delete: "destructive",
  soft_delete: "destructive",
  bulk_update: "warning",
  update: "warning",
  create: "success",
};

const OPERATION_LABELS: Record<string, string> = {
  create: "Create",
  update: "Update",
  delete: "Delete",
  bulk_update: "Bulk Update",
  soft_delete: "Soft Delete",
};

const ALL_OPERATIONS = ["create", "update", "delete", "bulk_update", "soft_delete"] as const;

const rowVariants: Variants = {
  hidden: { opacity: 0, height: 0 },
  show: { opacity: 1, height: "auto", transition: { duration: 0.2 } },
  exit: { opacity: 0, height: 0, transition: { duration: 0.15 } },
};

function AuditRow({ entry }: { entry: AuditEntry }) {
  const [expanded, setExpanded] = useState(false);
  const opVariant = OPERATION_VARIANTS[entry.action] ?? "default";
  const opLabel = OPERATION_LABELS[entry.action] ?? entry.action;

  return (
    <div className="border-b border-border/30 last:border-0">
      {/* Main row */}
      <button
        onClick={() => setExpanded((v) => !v)}
        className={cn(
          "w-full flex items-center gap-3 px-4 py-3 text-left",
          "hover:bg-accent/40 transition-colors duration-100",
          "focus-visible:outline-none focus-visible:bg-accent/40"
        )}
        aria-expanded={expanded}
      >
        <span className="text-muted-foreground shrink-0">
          {expanded ? (
            <ChevronDown className="h-3.5 w-3.5" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5" />
          )}
        </span>

        <Badge variant={opVariant} className="text-[10px] shrink-0 w-20 justify-center">
          {opLabel}
        </Badge>

        <span className="font-mono text-xs text-foreground/80 shrink-0 min-w-[80px]">
          {entry.table_name}
        </span>

        <span className="flex-1 truncate text-xs text-muted-foreground text-left">
          {entry.question || "—"}
        </span>

        <span className="text-xs tabular-nums text-foreground shrink-0">
          {formatNumber(entry.affected_rows)} rows
        </span>

        <span className="text-[11px] text-muted-foreground shrink-0 min-w-[64px] text-right">
          {formatRelativeTime(entry.timestamp)}
        </span>
      </button>

      {/* Expanded detail */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            variants={rowVariants}
            initial="hidden"
            animate="show"
            exit="exit"
            className="overflow-hidden"
          >
            <div className="mx-4 mb-3 rounded-lg border border-border/40 bg-muted/20 p-4 space-y-3">
              <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs">
                <div>
                  <span className="text-muted-foreground block mb-0.5">Audit ID</span>
                  <span className="font-mono text-foreground">{entry.audit_id}</span>
                </div>
                <div>
                  <span className="text-muted-foreground block mb-0.5">Timestamp</span>
                  <span className="text-foreground">
                    {new Date(entry.timestamp).toLocaleString()}
                  </span>
                </div>
                <div>
                  <span className="text-muted-foreground block mb-0.5">Table</span>
                  <span className="font-mono text-foreground">
                    {entry.schema_name ? `${entry.schema_name}.` : ""}{entry.table_name}
                  </span>
                </div>
                <div>
                  <span className="text-muted-foreground block mb-0.5">Duration</span>
                  <span className="tabular-nums text-foreground">
                    {entry.execution_time_ms.toFixed(1)} ms
                  </span>
                </div>
                {entry.rollback_token && (
                  <div className="col-span-2">
                    <span className="text-muted-foreground block mb-0.5">Rollback token</span>
                    <span className="font-mono text-[11px] break-all text-foreground/80">
                      {entry.rollback_token}
                    </span>
                  </div>
                )}
              </div>

              {entry.filters && entry.filters.length > 0 && (
                <div>
                  <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide block mb-1.5">
                    Filters
                  </span>
                  <div className="space-y-1">
                    {entry.filters.map((f, i) => (
                      <p key={i} className="font-mono text-[11px] text-foreground/80">
                        {String(f.column)} {String(f.operator)} {JSON.stringify(f.value)}
                      </p>
                    ))}
                  </div>
                </div>
              )}

              {entry.set_values && Object.keys(entry.set_values).length > 0 && (
                <div>
                  <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide block mb-1.5">
                    Set values
                  </span>
                  <div className="space-y-1">
                    {Object.entries(entry.set_values).map(([k, v]) => (
                      <p key={k} className="font-mono text-[11px] text-foreground/80">
                        {k} = {JSON.stringify(v)}
                      </p>
                    ))}
                  </div>
                </div>
              )}

              {entry.row_data && Object.keys(entry.row_data).length > 0 && (
                <div>
                  <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide block mb-1.5">
                    Row data
                  </span>
                  <pre className="text-[11px] font-mono text-foreground/80 bg-muted/30 rounded p-2 overflow-x-auto">
                    {JSON.stringify(entry.row_data, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function AuditSkeleton() {
  return (
    <div className="space-y-0">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="flex items-center gap-3 px-4 py-3 border-b border-border/30">
          <Skeleton className="h-3.5 w-3.5 rounded" />
          <Skeleton className="h-5 w-20 rounded-full" />
          <Skeleton className="h-3.5 w-20" />
          <Skeleton className="h-3.5 flex-1" />
          <Skeleton className="h-3.5 w-14" />
          <Skeleton className="h-3.5 w-12" />
        </div>
      ))}
    </div>
  );
}

interface CrudAuditViewerProps {
  connectionId: string | null;
}

export function CrudAuditViewer({ connectionId }: CrudAuditViewerProps) {
  const [search, setSearch] = useState("");
  const [opFilter, setOpFilter] = useState<string>("all");

  const { data, isLoading, refetch, isFetching } = useCrudAudit(connectionId);
  const entries = data?.entries ?? [];

  const filtered = entries.filter((e) => {
    const matchesSearch =
      !search ||
      e.question.toLowerCase().includes(search.toLowerCase()) ||
      e.table_name.toLowerCase().includes(search.toLowerCase());
    const matchesOp = opFilter === "all" || e.action === opFilter;
    return matchesSearch && matchesOp;
  });

  if (!connectionId) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <Search className="h-8 w-8 text-muted-foreground/30 mb-3" aria-hidden="true" />
        <p className="text-sm text-muted-foreground">Select a connection to view the audit log</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center gap-3 flex-wrap">
        {/* Search */}
        <div className="relative flex-1 min-w-[180px]">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground/50" />
          <input
            type="text"
            placeholder="Search questions or tables…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className={cn(
              "w-full rounded-lg border border-border/60 bg-card/60 pl-8 pr-3 py-1.5",
              "text-xs text-foreground placeholder:text-muted-foreground/50",
              "focus:outline-none focus:border-primary/50 transition-colors"
            )}
          />
        </div>

        {/* Operation filter */}
        <div className="flex items-center gap-1 flex-wrap">
          <button
            onClick={() => setOpFilter("all")}
            className={cn(
              "rounded-full px-3 py-1 text-[11px] font-medium border transition-colors",
              opFilter === "all"
                ? "bg-primary text-primary-foreground border-primary"
                : "border-border/50 text-muted-foreground hover:text-foreground hover:border-border"
            )}
          >
            All
          </button>
          {ALL_OPERATIONS.map((op) => (
            <button
              key={op}
              onClick={() => setOpFilter(op)}
              className={cn(
                "rounded-full px-3 py-1 text-[11px] font-medium border transition-colors",
                opFilter === op
                  ? "bg-primary text-primary-foreground border-primary"
                  : "border-border/50 text-muted-foreground hover:text-foreground hover:border-border"
              )}
            >
              {OPERATION_LABELS[op]}
            </button>
          ))}
        </div>

        {/* Refresh */}
        <Button
          variant="ghost"
          size="sm"
          className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground shrink-0"
          onClick={() => refetch()}
          disabled={isFetching}
          aria-label="Refresh audit log"
        >
          <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} />
        </Button>
      </div>

      {/* Table */}
      <div className="rounded-xl border border-border/50 bg-card/40 overflow-hidden">
        {/* Header row */}
        <div className="flex items-center gap-3 px-4 py-2 border-b border-border/50 bg-muted/20">
          <span className="w-3.5 shrink-0" />
          <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide w-20 shrink-0">
            Operation
          </span>
          <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide w-20 shrink-0">
            Table
          </span>
          <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide flex-1">
            Question
          </span>
          <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide w-14 text-right shrink-0">
            Rows
          </span>
          <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide w-16 text-right shrink-0">
            When
          </span>
        </div>

        {isLoading ? (
          <AuditSkeleton />
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <p className="text-sm text-muted-foreground">
              {entries.length === 0
                ? "No audit entries yet for this connection"
                : "No entries match the current filters"}
            </p>
          </div>
        ) : (
          <div>
            {filtered.map((entry) => (
              <AuditRow key={entry.audit_id} entry={entry} />
            ))}
          </div>
        )}
      </div>

      {data && (
        <p className="text-[11px] text-muted-foreground text-right">
          {filtered.length} of {data.count} entr{data.count === 1 ? "y" : "ies"}
        </p>
      )}
    </div>
  );
}
