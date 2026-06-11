"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { Variants } from "framer-motion";
import {
  BarChart2,
  CheckCircle2,
  ChevronDown,
  Clock,
  Code2,
  Database,
  Eye,
  FileText,
  LineChart,
  PenLine,
  TrendingUp,
  XCircle,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { ToolResult } from "@/lib/api/types";

// ── Tool metadata ─────────────────────────────────────────────────────────────

const TOOL_META: Record<
  string,
  { icon: React.ElementType; color: string; glow: string; label: string }
> = {
  dataset_preview: {
    icon: Database, label: "Dataset",
    color: "text-sky-400", glow: "bg-sky-400/10 border-sky-400/25",
  },
  analytics: {
    icon: BarChart2, label: "Analytics",
    color: "text-indigo-400", glow: "bg-indigo-400/10 border-indigo-400/25",
  },
  visualization: {
    icon: LineChart, label: "Viz",
    color: "text-violet-400", glow: "bg-violet-400/10 border-violet-400/25",
  },
  forecast: {
    icon: TrendingUp, label: "Forecast",
    color: "text-emerald-400", glow: "bg-emerald-400/10 border-emerald-400/25",
  },
  report: {
    icon: FileText, label: "Report",
    color: "text-amber-400", glow: "bg-amber-400/10 border-amber-400/25",
  },
  crud_preview: {
    icon: Eye, label: "Preview",
    color: "text-orange-400", glow: "bg-orange-400/10 border-orange-400/25",
  },
  crud_execute: {
    icon: PenLine, label: "Execute",
    color: "text-red-400", glow: "bg-red-400/10 border-red-400/25",
  },
  sql_query: {
    icon: Code2, label: "SQL",
    color: "text-cyan-400", glow: "bg-cyan-400/10 border-cyan-400/25",
  },
};

const expandVariants: Variants = {
  collapsed: { height: 0, opacity: 0 },
  expanded: {
    height: "auto",
    opacity: 1,
    transition: { duration: 0.2, ease: "easeOut" },
  },
};

function fmtMs(ms: number): string {
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
}

// ── Single step card ──────────────────────────────────────────────────────────

interface TimelineStepProps {
  step: ToolResult;
  index: number;
  isLast: boolean;
}

function TimelineStep({ step, index, isLast }: TimelineStepProps) {
  const [open, setOpen] = useState(false);
  const meta = TOOL_META[step.tool_name];
  const Icon = meta?.icon ?? Zap;
  const failed = !!step.error;

  return (
    <motion.div
      initial={{ opacity: 0, x: 10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.2, delay: index * 0.04, ease: "easeOut" }}
      className="flex gap-3"
    >
      {/* Left: step number + connector */}
      <div className="flex flex-col items-center shrink-0 w-6">
        <div
          className={cn(
            "flex h-6 w-6 items-center justify-center rounded-full border text-[10px] font-bold z-10 shrink-0",
            failed
              ? "border-destructive/40 bg-destructive/10 text-destructive"
              : "border-primary/30 bg-primary/10 text-primary"
          )}
        >
          {index + 1}
        </div>
        {!isLast && (
          <div className="w-px flex-1 mt-1 min-h-[16px] bg-border/40" />
        )}
      </div>

      {/* Right: card */}
      <div className={cn("flex-1 min-w-0", isLast ? "mb-0" : "mb-3")}>
        <div className="rounded-lg border border-border/40 bg-card/50 overflow-hidden">
          {/* Header */}
          <button
            className="w-full flex items-center gap-2.5 px-3 py-2.5 text-left hover:bg-muted/20 transition-colors duration-150"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
          >
            {/* Tool icon badge */}
            <div
              className={cn(
                "flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border",
                meta?.glow ?? "bg-muted/20 border-border/40"
              )}
            >
              <Icon
                className={cn("h-3.5 w-3.5", meta?.color ?? "text-muted-foreground")}
                aria-hidden="true"
              />
            </div>

            <div className="flex-1 min-w-0">
              <p className="text-xs font-semibold text-foreground truncate leading-tight">
                {step.step_label}
              </p>
              <p
                className={cn(
                  "text-[10px] font-mono mt-0.5 truncate",
                  meta?.color ?? "text-muted-foreground/60"
                )}
              >
                {meta?.label ?? step.tool_name}
              </p>
            </div>

            <div className="flex items-center gap-1.5 shrink-0">
              {failed ? (
                <XCircle className="h-3.5 w-3.5 text-destructive" aria-label="Failed" />
              ) : (
                <CheckCircle2
                  className="h-3.5 w-3.5 text-[hsl(var(--success))]"
                  aria-label="Success"
                />
              )}
              <span className="text-[10px] text-muted-foreground/50 tabular-nums">
                {fmtMs(step.duration_ms)}
              </span>
              <ChevronDown
                className={cn(
                  "h-3 w-3 text-muted-foreground/40 transition-transform duration-200",
                  open && "rotate-180"
                )}
                aria-hidden="true"
              />
            </div>
          </button>

          {/* Expandable output */}
          <AnimatePresence initial={false}>
            {open && (
              <motion.div
                key="detail"
                variants={expandVariants}
                initial="collapsed"
                animate="expanded"
                exit="collapsed"
                className="overflow-hidden"
              >
                <div className="px-3 pb-3 pt-0 border-t border-border/30">
                  {step.error ? (
                    <div className="mt-2 rounded-md border border-destructive/30 bg-destructive/5 px-2.5 py-2">
                      <p className="text-[11px] text-destructive font-mono whitespace-pre-wrap break-all">
                        {step.error}
                      </p>
                    </div>
                  ) : (
                    <pre className="mt-2 text-[10px] font-mono text-muted-foreground/80 bg-muted/20 rounded-md px-2.5 py-2 overflow-x-auto whitespace-pre-wrap break-all max-h-40 overflow-y-auto">
                      {JSON.stringify(step.output, null, 2)}
                    </pre>
                  )}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </motion.div>
  );
}

// ── Live "next step" pulse ────────────────────────────────────────────────────

function PendingStep({ index }: { index: number }) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="flex gap-3"
    >
      <div className="flex flex-col items-center shrink-0 w-6">
        <motion.div
          className="flex h-6 w-6 items-center justify-center rounded-full border border-primary/40 bg-primary/10"
          animate={{ scale: [1, 1.15, 1], opacity: [0.6, 1, 0.6] }}
          transition={{ duration: 1.5, repeat: Infinity }}
        >
          <span className="text-[10px] font-bold text-primary">{index + 1}</span>
        </motion.div>
      </div>

      <div className="flex-1 flex items-center h-6 gap-1">
        {[0, 1, 2].map((i) => (
          <motion.span
            key={i}
            className="inline-block h-1 w-1 rounded-full bg-primary/40"
            animate={{ opacity: [0.3, 1, 0.3] }}
            transition={{ duration: 1, repeat: Infinity, delay: i * 0.2 }}
          />
        ))}
      </div>
    </motion.div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

interface AgentTimelineProps {
  steps: ToolResult[];
  isPending?: boolean;
}

export function AgentTimeline({ steps, isPending }: AgentTimelineProps) {
  const totalMs = steps.reduce((acc, s) => acc + s.duration_ms, 0);
  const failedCount = steps.filter((s) => s.error).length;

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-border/60 shrink-0">
        <div className="flex items-center gap-2">
          <Zap className="h-3.5 w-3.5 text-muted-foreground/60" aria-hidden="true" />
          <span className="text-xs font-semibold text-foreground">
            Execution trace
          </span>
        </div>

        {steps.length > 0 && (
          <div className="flex items-center gap-2 text-[10px] text-muted-foreground/50">
            <span className="tabular-nums font-medium text-foreground/80">
              {steps.length}
            </span>
            <span>step{steps.length !== 1 ? "s" : ""}</span>
            {totalMs > 0 && (
              <>
                <span className="text-muted-foreground/25">·</span>
                <span className="flex items-center gap-0.5 tabular-nums">
                  <Clock className="h-2.5 w-2.5" aria-hidden="true" />
                  {fmtMs(totalMs)}
                </span>
              </>
            )}
            {failedCount > 0 && (
              <>
                <span className="text-muted-foreground/25">·</span>
                <span className="text-destructive tabular-nums">
                  {failedCount} err
                </span>
              </>
            )}
          </div>
        )}
      </div>

      {/* Body */}
      {steps.length === 0 && !isPending ? (
        <div className="flex flex-col items-center justify-center flex-1 text-center px-5 py-8 gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-muted/20">
            <Zap className="h-5 w-5 text-muted-foreground/20" aria-hidden="true" />
          </div>
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground">
              No tool calls yet
            </p>
            <p className="text-[11px] text-muted-foreground/50 leading-relaxed">
              Run a goal to see step-by-step execution
            </p>
          </div>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto p-4">
          {steps.map((step, i) => (
            <TimelineStep
              key={`${step.tool_name}-${i}`}
              step={step}
              index={i}
              isLast={i === steps.length - 1 && !isPending}
            />
          ))}

          {isPending && <PendingStep index={steps.length} />}
        </div>
      )}
    </div>
  );
}
