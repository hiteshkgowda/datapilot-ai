"use client";

import { motion } from "framer-motion";
import type { Variants } from "framer-motion";
import {
  BarChart2,
  CheckCircle2,
  Code2,
  Database,
  Eye,
  FileText,
  Lightbulb,
  LineChart,
  PenLine,
  TrendingUp,
  XCircle,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import type { AgentExplainTurn } from "./types";

// ── Tool metadata ─────────────────────────────────────────────────────────────

const TOOL_META: Record<
  string,
  { label: string; icon: React.ElementType; color: string; glow: string }
> = {
  dataset_preview: {
    label: "Dataset", icon: Database,
    color: "text-sky-400", glow: "bg-sky-400/10 border-sky-400/20",
  },
  analytics: {
    label: "Analytics", icon: BarChart2,
    color: "text-indigo-400", glow: "bg-indigo-400/10 border-indigo-400/20",
  },
  visualization: {
    label: "Visualization", icon: LineChart,
    color: "text-violet-400", glow: "bg-violet-400/10 border-violet-400/20",
  },
  forecast: {
    label: "Forecast", icon: TrendingUp,
    color: "text-emerald-400", glow: "bg-emerald-400/10 border-emerald-400/20",
  },
  report: {
    label: "Report", icon: FileText,
    color: "text-amber-400", glow: "bg-amber-400/10 border-amber-400/20",
  },
  crud_preview: {
    label: "CRUD Preview", icon: Eye,
    color: "text-orange-400", glow: "bg-orange-400/10 border-orange-400/20",
  },
  crud_execute: {
    label: "CRUD Execute", icon: PenLine,
    color: "text-red-400", glow: "bg-red-400/10 border-red-400/20",
  },
  sql_query: {
    label: "SQL Query", icon: Code2,
    color: "text-cyan-400", glow: "bg-cyan-400/10 border-cyan-400/20",
  },
};

const stepVariants: Variants = {
  hidden: { opacity: 0, y: 8 },
  show: (i: number) => ({
    opacity: 1, y: 0,
    transition: { duration: 0.2, ease: "easeOut", delay: i * 0.06 },
  }),
};

interface AgentExplainPanelProps {
  turn: AgentExplainTurn;
}

export function AgentExplainPanel({ turn }: AgentExplainPanelProps) {
  const { explain, goal } = turn;
  const { plan, plan_valid, warnings, error } = explain;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      className="rounded-xl border border-border/50 bg-card/60 backdrop-blur-sm overflow-hidden"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border/40 bg-muted/10">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-primary/10">
            <Lightbulb className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
          </div>
          <div className="min-w-0">
            <p className="text-xs font-semibold text-foreground flex items-center gap-1.5">
              Execution plan
            </p>
            <p
              className="text-[11px] text-muted-foreground truncate max-w-[280px]"
              title={goal}
            >
              {goal}
            </p>
          </div>
        </div>

        <Badge
          variant={plan_valid ? "success" : "destructive"}
          className="shrink-0 gap-1"
        >
          {plan_valid ? (
            <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
          ) : (
            <XCircle className="h-3 w-3" aria-hidden="true" />
          )}
          {plan_valid ? "Valid" : "Invalid"}
        </Badge>
      </div>

      {/* Body */}
      <div className="p-4 space-y-4">
        {/* Error */}
        {error && (
          <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2.5">
            <p className="text-xs text-destructive">{error}</p>
          </div>
        )}

        {/* Warnings */}
        {warnings.length > 0 && (
          <div className="space-y-1">
            {warnings.map((w, i) => (
              <p key={i} className="text-[11px] text-warning flex items-start gap-1.5">
                <span aria-hidden="true">⚠</span>
                {w}
              </p>
            ))}
          </div>
        )}

        {/* Plan steps */}
        {plan.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No steps generated. The plan may have been rejected by the verifier.
          </p>
        ) : (
          <div>
            {plan.map((step, i) => {
              const meta = TOOL_META[step.tool_name];
              const Icon = meta?.icon ?? Zap;
              const isLast = i === plan.length - 1;

              return (
                <div key={i} className="flex gap-3">
                  {/* Left: number + connector */}
                  <div className="flex flex-col items-center shrink-0 w-6">
                    <motion.div
                      custom={i}
                      variants={stepVariants}
                      initial="hidden"
                      animate="show"
                      className="flex h-6 w-6 items-center justify-center rounded-full border border-primary/30 bg-primary/10 text-[10px] font-bold text-primary z-10 shrink-0"
                    >
                      {i + 1}
                    </motion.div>
                    {!isLast && (
                      <div className="w-px flex-1 mt-1 min-h-[12px] bg-border/40" />
                    )}
                  </div>

                  {/* Right: step card */}
                  <motion.div
                    custom={i}
                    variants={stepVariants}
                    initial="hidden"
                    animate="show"
                    className={cn("flex-1 min-w-0", isLast ? "mb-0" : "mb-3")}
                  >
                    <div className="flex items-start gap-2.5 rounded-lg border border-border/40 bg-muted/10 px-3 py-2.5">
                      {/* Tool icon */}
                      <div
                        className={cn(
                          "flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border mt-0.5",
                          meta?.glow ?? "bg-muted/20 border-border/40"
                        )}
                      >
                        <Icon
                          className={cn(
                            "h-3.5 w-3.5",
                            meta?.color ?? "text-muted-foreground"
                          )}
                          aria-hidden="true"
                        />
                      </div>

                      <div className="flex-1 min-w-0">
                        {/* Label row */}
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-xs font-semibold text-foreground">
                            {step.step_label}
                          </span>
                          <span
                            className={cn(
                              "text-[10px] font-mono px-1.5 py-0.5 rounded bg-muted/30",
                              meta?.color ?? "text-muted-foreground"
                            )}
                          >
                            {meta?.label ?? step.tool_name}
                          </span>
                          {step.requires_approval && (
                            <Badge variant="warning" className="text-[10px] h-4 px-1.5">
                              Needs approval
                            </Badge>
                          )}
                        </div>

                        {/* Arguments */}
                        {Object.keys(step.arguments).length > 0 && (
                          <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5">
                            {Object.entries(step.arguments)
                              .filter(([, v]) => v !== null && v !== undefined && v !== "")
                              .slice(0, 4)
                              .map(([k, v]) => (
                                <span key={k} className="text-[10px] text-muted-foreground/60">
                                  <span className="font-medium text-muted-foreground/80">
                                    {k}
                                  </span>
                                  {" "}
                                  <span className="font-mono">
                                    {String(v).slice(0, 30)}
                                  </span>
                                </span>
                              ))}
                          </div>
                        )}
                      </div>
                    </div>
                  </motion.div>
                </div>
              );
            })}
          </div>
        )}

        {/* Footer note */}
        <p className="text-[10px] text-muted-foreground/40">
          {plan.length} step{plan.length !== 1 ? "s" : ""} planned · no tools were executed
        </p>
      </div>
    </motion.div>
  );
}
