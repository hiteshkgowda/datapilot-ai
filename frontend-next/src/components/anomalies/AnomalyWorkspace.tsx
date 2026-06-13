"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import type { Variants } from "framer-motion";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  ChevronDown,
  Database,
  Loader2,
  ScanSearch,
  Zap,
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { detectAnomalies } from "@/lib/api/anomalies";
import { ApiError } from "@/lib/api/client";
import { PlotlyChart } from "@/components/ask/PlotlyChart";
import { Button } from "@/components/ui/button";
import type {
  AnomalyMethod,
  AnomalyResponse,
  AnomalySeverity,
  ColumnAnomaly,
} from "@/lib/api/types";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const SEVERITY_STYLES: Record<AnomalySeverity, { badge: string; dot: string; label: string }> = {
  none:     { badge: "bg-muted/50 text-muted-foreground",           dot: "bg-muted-foreground",  label: "None" },
  low:      { badge: "bg-yellow-500/10 text-yellow-500",            dot: "bg-yellow-400",         label: "Low" },
  medium:   { badge: "bg-amber-500/10 text-amber-500",              dot: "bg-amber-400",          label: "Medium" },
  high:     { badge: "bg-orange-500/10 text-orange-500",            dot: "bg-orange-400",         label: "High" },
  critical: { badge: "bg-red-500/10 text-red-500 font-semibold",    dot: "bg-red-500",            label: "Critical" },
};

const METHOD_LABELS: Record<AnomalyMethod, string> = {
  zscore:            "Z-Score",
  iqr:               "IQR",
  isolation_forest:  "Isolation Forest",
  seasonal:          "Seasonal",
};

const ALL_METHODS: AnomalyMethod[] = ["zscore", "iqr", "isolation_forest", "seasonal"];

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function SeverityBadge({ severity }: { severity: AnomalySeverity }) {
  const s = SEVERITY_STYLES[severity] ?? SEVERITY_STYLES.none;
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs", s.badge)}>
      <span className={cn("h-1.5 w-1.5 rounded-full", s.dot)} />
      {s.label}
    </span>
  );
}

function MethodTag({ method }: { method: AnomalyMethod }) {
  return (
    <span className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-mono bg-muted/60 text-muted-foreground">
      {METHOD_LABELS[method] ?? method}
    </span>
  );
}

const collapseVariants: Variants = {
  hidden: { height: 0, opacity: 0 },
  show:   { height: "auto", opacity: 1, transition: { duration: 0.18, ease: "easeOut" } },
  exit:   { height: 0, opacity: 0, transition: { duration: 0.14, ease: "easeIn" } },
};

function ColumnAnomalyCard({ ca }: { ca: ColumnAnomaly }) {
  const [open, setOpen] = useState(false);
  const worst = ca.anomaly_points.reduce(
    (best, p) => (p.score > best.score ? p : best),
    ca.anomaly_points[0]
  );

  return (
    <div className="rounded-xl border border-border/60 bg-card overflow-hidden">
      <button
        className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left hover:bg-muted/20 transition-colors"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <div className="flex items-center gap-3 min-w-0">
          <span className="font-mono text-sm font-medium text-foreground truncate">
            {ca.column}
          </span>
          <SeverityBadge severity={worst?.severity ?? "low"} />
          <span className="text-xs text-muted-foreground tabular-nums">
            {ca.anomaly_count} anomaly/anomalies
          </span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {ca.methods.map((m) => <MethodTag key={m} method={m} />)}
          <ChevronDown
            className={cn("h-4 w-4 text-muted-foreground transition-transform", open && "rotate-180")}
          />
        </div>
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            variants={collapseVariants}
            initial="hidden"
            animate="show"
            exit="exit"
            className="overflow-hidden"
          >
            <div className="px-4 pb-4 space-y-3 border-t border-border/40 pt-3">
              {/* Stats row */}
              <div className="grid grid-cols-4 gap-2">
                {[
                  { label: "Mean",  value: ca.mean.toLocaleString(undefined, { maximumFractionDigits: 2 }) },
                  { label: "Std",   value: ca.std.toLocaleString(undefined,  { maximumFractionDigits: 2 }) },
                  { label: "Q1",    value: ca.q1.toLocaleString(undefined,   { maximumFractionDigits: 2 }) },
                  { label: "Q3",    value: ca.q3.toLocaleString(undefined,   { maximumFractionDigits: 2 }) },
                ].map(({ label, value }) => (
                  <div key={label} className="rounded-lg bg-muted/30 px-3 py-2">
                    <p className="text-[10px] text-muted-foreground mb-0.5">{label}</p>
                    <p className="text-xs font-mono font-medium tabular-nums">{value}</p>
                  </div>
                ))}
              </div>

              {/* Anomaly points table */}
              <div className="overflow-x-auto rounded-lg border border-border/40">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="bg-muted/30 text-muted-foreground">
                      <th className="px-3 py-2 text-left font-medium">Row</th>
                      <th className="px-3 py-2 text-left font-medium">Value</th>
                      <th className="px-3 py-2 text-left font-medium">Score</th>
                      <th className="px-3 py-2 text-left font-medium">Severity</th>
                      <th className="px-3 py-2 text-left font-medium">Method</th>
                      <th className="px-3 py-2 text-left font-medium">Label</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ca.anomaly_points.slice(0, 20).map((pt) => (
                      <tr
                        key={`${pt.row_index}-${pt.method}`}
                        className="border-t border-border/30 hover:bg-muted/10"
                      >
                        <td className="px-3 py-1.5 font-mono tabular-nums text-muted-foreground">{pt.row_index}</td>
                        <td className="px-3 py-1.5 font-mono tabular-nums">{pt.value.toLocaleString(undefined, { maximumFractionDigits: 4 })}</td>
                        <td className="px-3 py-1.5 font-mono tabular-nums">{pt.score.toFixed(3)}</td>
                        <td className="px-3 py-1.5"><SeverityBadge severity={pt.severity} /></td>
                        <td className="px-3 py-1.5"><MethodTag method={pt.method} /></td>
                        <td className="px-3 py-1.5 text-muted-foreground">{pt.label ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {ca.anomaly_points.length > 20 && (
                  <p className="px-3 py-2 text-xs text-muted-foreground border-t border-border/30">
                    … and {ca.anomaly_points.length - 20} more points
                  </p>
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Configuration panel
// ---------------------------------------------------------------------------

interface ConfigState {
  methods: AnomalyMethod[];
  zscore_threshold: number;
  iqr_multiplier: number;
  contamination: number;
  time_column: string;
}

function ConfigPanel({
  config,
  onChange,
}: {
  config: ConfigState;
  onChange: (c: ConfigState) => void;
}) {
  const toggle = (m: AnomalyMethod) => {
    const next = config.methods.includes(m)
      ? config.methods.filter((x) => x !== m)
      : [...config.methods, m];
    if (next.length > 0) onChange({ ...config, methods: next });
  };

  return (
    <div className="rounded-xl border border-border/60 bg-card/60 p-4 space-y-4">
      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
        Detection Configuration
      </p>

      {/* Methods */}
      <div>
        <p className="text-xs text-muted-foreground mb-2">Methods</p>
        <div className="flex flex-wrap gap-2">
          {ALL_METHODS.map((m) => (
            <button
              key={m}
              onClick={() => toggle(m)}
              className={cn(
                "rounded-lg px-2.5 py-1 text-xs font-mono transition-colors",
                config.methods.includes(m)
                  ? "bg-primary/10 text-primary border border-primary/30"
                  : "bg-muted/40 text-muted-foreground border border-transparent hover:border-border/60"
              )}
            >
              {METHOD_LABELS[m]}
            </button>
          ))}
        </div>
      </div>

      {/* Numeric params */}
      <div className="grid grid-cols-3 gap-3">
        {[
          { key: "zscore_threshold", label: "Z-Score threshold", min: 1, max: 10, step: 0.5 },
          { key: "iqr_multiplier",   label: "IQR multiplier",    min: 0.5, max: 5, step: 0.5 },
          { key: "contamination",    label: "Contamination",     min: 0.01, max: 0.5, step: 0.01 },
        ].map(({ key, label, min, max, step }) => (
          <div key={key}>
            <label className="text-[10px] text-muted-foreground block mb-1">{label}</label>
            <input
              type="number"
              min={min}
              max={max}
              step={step}
              value={config[key as keyof ConfigState] as number}
              onChange={(e) =>
                onChange({ ...config, [key]: parseFloat(e.target.value) || min })
              }
              className="w-full rounded-lg border border-border/60 bg-background px-2.5 py-1 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>
        ))}
      </div>

      {/* Time column */}
      <div>
        <label className="text-[10px] text-muted-foreground block mb-1">
          Time column (optional)
        </label>
        <input
          type="text"
          placeholder="e.g. date, month, period"
          value={config.time_column}
          onChange={(e) => onChange({ ...config, time_column: e.target.value })}
          className="w-full rounded-lg border border-border/60 bg-background px-2.5 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-ring"
        />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main workspace
// ---------------------------------------------------------------------------

interface AnomalyWorkspaceProps {
  datasetId: string;
}

export function AnomalyWorkspace({ datasetId }: AnomalyWorkspaceProps) {
  const [result, setResult] = useState<AnomalyResponse | null>(null);
  const [config, setConfig] = useState<ConfigState>({
    methods: ["zscore", "iqr", "isolation_forest", "seasonal"],
    zscore_threshold: 3.0,
    iqr_multiplier: 1.5,
    contamination: 0.05,
    time_column: "",
  });

  const mutation = useMutation({
    mutationFn: () =>
      detectAnomalies({
        dataset_id: datasetId,
        methods: config.methods,
        zscore_threshold: config.zscore_threshold,
        iqr_multiplier: config.iqr_multiplier,
        contamination: config.contamination,
        time_column: config.time_column || undefined,
      }),
    onSuccess: (data) => setResult(data),
    onError: (err: unknown) => {
      const message =
        err instanceof ApiError ? err.message : "Anomaly detection failed. Please try again.";
      toast.error(message);
    },
  });

  const sev = result?.severity ?? "none";
  const sevStyle = SEVERITY_STYLES[sev];

  return (
    <div className="flex flex-col h-full bg-background">
      {/* ── Header ──────────────────────────────────────────────────── */}
      <header className="flex h-11 shrink-0 items-center justify-between border-b border-border/40 bg-background/95 backdrop-blur-sm px-3">
        <div className="flex items-center gap-1 min-w-0">
          <Link
            href={`/datasets/${datasetId}`}
            aria-label="Back to dataset"
            className="flex h-7 w-7 items-center justify-center rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          </Link>
          <div className="h-4 w-px bg-border/60 mx-1 shrink-0" />
          <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-orange-500/10">
            <AlertTriangle className="h-3 w-3 text-orange-500" />
          </div>
          <span className="ml-1.5 text-sm font-medium text-foreground">Anomaly Detection</span>
        </div>

        {result && (
          <div className="flex items-center gap-2">
            <SeverityBadge severity={sev} />
            <span className="text-xs text-muted-foreground tabular-nums">
              {result.total_anomaly_count} total
            </span>
            <span className="text-xs text-muted-foreground/40">·</span>
            <span className="text-xs text-muted-foreground tabular-nums">
              {(result.detection_time_ms / 1000).toFixed(2)}s
            </span>
          </div>
        )}
      </header>

      {/* ── Body ────────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-4xl mx-auto px-4 py-6 space-y-6">
          {/* Config + run */}
          <div className="space-y-3">
            <ConfigPanel config={config} onChange={setConfig} />
            <Button
              onClick={() => mutation.mutate()}
              disabled={mutation.isPending}
              className="w-full gap-2"
            >
              {mutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <ScanSearch className="h-4 w-4" />
              )}
              {mutation.isPending ? "Scanning for anomalies…" : "Run Anomaly Detection"}
            </Button>
          </div>

          {/* Results */}
          {result && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.22 }}
              className="space-y-5"
            >
              {/* Summary banner */}
              <div
                className={cn(
                  "rounded-xl border p-4 flex items-start gap-3",
                  sev === "none" || sev === "low"
                    ? "border-green-500/20 bg-green-500/5"
                    : sev === "medium"
                    ? "border-amber-500/20 bg-amber-500/5"
                    : sev === "high"
                    ? "border-orange-500/20 bg-orange-500/5"
                    : "border-red-500/20 bg-red-500/5"
                )}
              >
                {result.total_anomaly_count === 0 ? (
                  <CheckCircle2 className="h-4 w-4 text-green-500 shrink-0 mt-0.5" />
                ) : (
                  <AlertTriangle className={cn("h-4 w-4 shrink-0 mt-0.5", sevStyle.dot.replace("bg-", "text-"))} />
                )}
                <div className="space-y-1 flex-1 min-w-0">
                  <p className="text-sm font-medium text-foreground">
                    {result.total_anomaly_count === 0
                      ? "No anomalies detected"
                      : `${result.total_anomaly_count} anomaly/anomalies across ${result.affected_metrics.length} metric(s)`}
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {result.methods_used.map((m) => <MethodTag key={m} method={m} />)}
                  </div>
                </div>
              </div>

              {/* Possible reasons */}
              {result.possible_reasons.length > 0 && (
                <div className="rounded-xl border border-border/60 bg-card/60 p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <Zap className="h-3.5 w-3.5 text-primary" />
                    <p className="text-xs font-medium text-foreground">Possible Reasons</p>
                  </div>
                  <ul className="space-y-2">
                    {result.possible_reasons.map((r, i) => (
                      <li key={i} className="flex items-start gap-2 text-xs text-muted-foreground leading-relaxed">
                        <span className="mt-1.5 h-1 w-1 rounded-full bg-muted-foreground/50 shrink-0" />
                        {r}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Chart */}
              {result.chart_spec && (
                <div className="rounded-xl border border-border/60 bg-card overflow-hidden">
                  <div className="flex items-center gap-2.5 border-b border-border/40 bg-muted/20 px-4 py-2.5">
                    <Database className="h-3.5 w-3.5 text-muted-foreground" />
                    <span className="text-xs font-medium text-muted-foreground">Anomaly Chart</span>
                  </div>
                  <div className="px-2 pb-2 pt-1">
                    <PlotlyChart spec={result.chart_spec} />
                  </div>
                </div>
              )}

              {/* Per-column results */}
              {result.anomalies.length > 0 && (
                <div className="space-y-2">
                  <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                    Affected Columns
                  </p>
                  {result.anomalies.map((ca) => (
                    <ColumnAnomalyCard key={ca.column} ca={ca} />
                  ))}
                </div>
              )}
            </motion.div>
          )}
        </div>
      </div>
    </div>
  );
}
