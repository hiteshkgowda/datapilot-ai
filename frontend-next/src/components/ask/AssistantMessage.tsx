"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { Variants } from "framer-motion";
import {
  AlertTriangle,
  BarChart2,
  ChevronDown,
  LineChart,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { formatRelativeTime } from "@/lib/format";
import { PlotlyChart } from "./PlotlyChart";
import { ResultTable } from "./ResultTable";
import type { AssistantTurn, ErrorTurn } from "./types";
import type { ChartType } from "@/lib/api/types";

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtMs(ms: number): string {
  return ms < 1000 ? `${Math.round(ms)}ms` : `${(ms / 1000).toFixed(2)}s`;
}

// ── Chart artifact card ───────────────────────────────────────────────────────

const CHART_ICONS: Partial<Record<ChartType, React.ElementType>> = {
  bar: BarChart2,
  line: LineChart,
};

interface ChartArtifactProps {
  spec: Record<string, unknown>;
  chartType: ChartType | null;
}

function ChartArtifact({ spec, chartType }: ChartArtifactProps) {
  const Icon = (chartType && CHART_ICONS[chartType]) ?? BarChart2;

  return (
    <div className="rounded-xl border border-border/60 bg-card overflow-hidden elevation-sm">
      {/* Header */}
      <div className="flex items-center gap-2.5 border-b border-border/40 bg-muted/20 px-4 py-2.5">
        <Icon className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
        <span className="text-xs font-medium text-muted-foreground capitalize">
          {chartType ?? "Chart"}
        </span>
      </div>
      {/* Chart */}
      <div className="px-2 pb-2 pt-1">
        <PlotlyChart spec={spec} />
      </div>
    </div>
  );
}

// ── Execution footer ──────────────────────────────────────────────────────────

const detailVariants: Variants = {
  hidden: { height: 0, opacity: 0 },
  show: { height: "auto", opacity: 1, transition: { duration: 0.18, ease: "easeOut" } },
  exit:  { height: 0, opacity: 0, transition: { duration: 0.14, ease: "easeIn" } },
};

interface ExecutionFooterProps {
  executionTimeMs: number;
  totalTimeMs: number;
  chartType: ChartType | null;
  timestamp: string;
}

function ExecutionFooter({
  executionTimeMs,
  totalTimeMs,
  chartType,
  timestamp,
}: ExecutionFooterProps) {
  const [open, setOpen] = useState(false);
  const llmMs = Math.max(0, totalTimeMs - executionTimeMs);

  return (
    <div className="space-y-1.5 pt-1">
      {/* One-liner trigger */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => setOpen((v) => !v)}
          className="flex items-center gap-1.5 text-[11px] text-muted-foreground/40 hover:text-muted-foreground/70 transition-colors duration-150 group"
          aria-expanded={open}
        >
          <Zap className="h-2.5 w-2.5" aria-hidden="true" />
          <span className="tabular-nums">{(totalTimeMs / 1000).toFixed(1)}s</span>
          <span aria-hidden="true">·</span>
          <span>QueryPlan</span>
          {chartType && (
            <>
              <span aria-hidden="true">·</span>
              <span className="capitalize">{chartType} chart</span>
            </>
          )}
          <ChevronDown
            className={cn(
              "h-2.5 w-2.5 transition-transform duration-150",
              open && "rotate-180"
            )}
            aria-hidden="true"
          />
        </button>

        <span className="text-[11px] text-muted-foreground/30 tabular-nums">
          {formatRelativeTime(timestamp)}
        </span>
      </div>

      {/* Expandable detail */}
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            variants={detailVariants}
            initial="hidden"
            animate="show"
            exit="exit"
            className="overflow-hidden"
          >
            <div className="grid grid-cols-3 gap-px rounded-lg border border-border/40 bg-border/40 overflow-hidden text-[11px]">
              {[
                { label: "Data engine", value: fmtMs(executionTimeMs) },
                { label: "LLM planning", value: fmtMs(llmMs) },
                { label: "Total", value: `${(totalTimeMs / 1000).toFixed(2)}s`, highlight: true },
              ].map(({ label, value, highlight }) => (
                <div key={label} className="bg-card px-3 py-2.5">
                  <p className="text-muted-foreground/50 mb-0.5">{label}</p>
                  <p
                    className={cn(
                      "font-mono font-medium tabular-nums",
                      highlight ? "text-primary" : "text-foreground"
                    )}
                  >
                    {value}
                  </p>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ── Error message ─────────────────────────────────────────────────────────────

interface ErrorMessageProps {
  turn: ErrorTurn;
}

export function ErrorMessage({ turn }: ErrorMessageProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: "easeOut" }}
      className="flex items-start gap-4"
    >
      {/* Avatar */}
      <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-destructive/10">
        <AlertTriangle className="h-3 w-3 text-destructive" aria-hidden="true" />
      </div>

      {/* Error text */}
      <div className="flex-1 min-w-0 rounded-xl border border-destructive/20 bg-destructive/5 px-4 py-3">
        <p className="text-sm text-destructive leading-relaxed">{turn.message}</p>
        <p className="mt-1.5 text-[11px] text-muted-foreground/40">
          {formatRelativeTime(turn.timestamp)}
        </p>
      </div>
    </motion.div>
  );
}

// ── Assistant message ─────────────────────────────────────────────────────────

interface AssistantMessageProps {
  turn: AssistantTurn;
}

export function AssistantMessage({ turn }: AssistantMessageProps) {
  const hasChart = turn.chart_spec !== null;
  const hasTable = turn.table_data.length > 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22, ease: "easeOut" }}
      className="flex items-start gap-4"
    >
      {/* Avatar — gradient dot, no card */}
      <div
        className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-gradient-primary elevation-glow-sm"
        aria-hidden="true"
      >
        <Zap className="h-3 w-3 text-white" />
      </div>

      {/* Content column */}
      <div className="flex-1 min-w-0 space-y-4">
        {/* ── Answer text — ambient, no card ────────────────────── */}
        <p className="text-sm text-foreground leading-[1.8] whitespace-pre-wrap">
          {turn.answer}
        </p>

        {/* ── Chart artifact ────────────────────────────────────── */}
        {hasChart && (
          <ChartArtifact
            spec={turn.chart_spec!}
            chartType={turn.chart_type}
          />
        )}

        {/* ── Table artifact ────────────────────────────────────── */}
        {hasTable && <ResultTable data={turn.table_data} />}

        {/* ── Execution footer ──────────────────────────────────── */}
        <ExecutionFooter
          executionTimeMs={turn.execution_time_ms}
          totalTimeMs={turn.total_time_ms}
          chartType={turn.chart_type}
          timestamp={turn.timestamp}
        />
      </div>
    </motion.div>
  );
}
