"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useMutation } from "@tanstack/react-query";
import { motion } from "framer-motion";
import type { Variants } from "framer-motion";
import {
  AlertTriangle,
  ArrowLeft,
  BarChart2,
  CheckCircle2,
  Database,
  GitBranch,
  Layers,
  Lightbulb,
  Loader2,
  RefreshCw,
  Rows3,
  Search,
  Sparkles,
  TrendingUp,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useDatasetPreview } from "@/hooks/use-datasets";
import { generateInsights } from "@/lib/api/insights";
import { detectAnomalies } from "@/lib/api/anomalies";
import { analyzeRootCause } from "@/lib/api/root-cause";
import { generateRecommendations } from "@/lib/api/recommendations";
import { PlotlyChart } from "@/components/ask/PlotlyChart";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import type {
  AnomalyResponse,
  AnomalySeverity,
  InsightResponse,
  RecommendationPriority,
  RecommendationResponse,
  RootCauseResponse,
} from "@/lib/api/types";

// ---------------------------------------------------------------------------
// Animations
// ---------------------------------------------------------------------------

const fadeIn: Variants = {
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0, transition: { duration: 0.22 } },
};

const stagger: Variants = {
  show: { transition: { staggerChildren: 0.07 } },
};

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

const SEVERITY_STYLES: Record<
  AnomalySeverity,
  { pill: string; dot: string; label: string; cardBorder: string }
> = {
  none: {
    pill: "bg-emerald-500/10 text-emerald-500",
    dot: "bg-emerald-500",
    label: "Healthy",
    cardBorder: "border-emerald-500/20 bg-emerald-500/5",
  },
  low: {
    pill: "bg-yellow-500/10 text-yellow-500",
    dot: "bg-yellow-400",
    label: "Low",
    cardBorder: "border-yellow-500/20 bg-yellow-500/5",
  },
  medium: {
    pill: "bg-amber-500/10 text-amber-500",
    dot: "bg-amber-400",
    label: "Medium",
    cardBorder: "border-amber-500/20 bg-amber-500/5",
  },
  high: {
    pill: "bg-orange-500/10 text-orange-500",
    dot: "bg-orange-400",
    label: "High",
    cardBorder: "border-orange-500/20 bg-orange-500/5",
  },
  critical: {
    pill: "bg-red-500/10 text-red-500",
    dot: "bg-red-500",
    label: "Critical",
    cardBorder: "border-red-500/20 bg-red-500/5",
  },
};

const PRIORITY_CONFIG: Record<
  RecommendationPriority,
  { label: string; cls: string; dot: string }
> = {
  critical: {
    label: "Critical",
    cls: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
    dot: "bg-red-500",
  },
  high: {
    label: "High",
    cls: "bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-300",
    dot: "bg-orange-500",
  },
  medium: {
    label: "Medium",
    cls: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300",
    dot: "bg-yellow-500",
  },
  low: {
    label: "Low",
    cls: "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300",
    dot: "bg-blue-500",
  },
};

const IMPACT_STYLES: Record<string, string> = {
  high: "bg-red-500/10 text-red-500",
  medium: "bg-amber-500/10 text-amber-500",
  low: "bg-blue-500/10 text-blue-500",
};

// ---------------------------------------------------------------------------
// Shared primitives
// ---------------------------------------------------------------------------

function SectionSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-2.5">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton
          key={i}
          className={cn(
            "h-4",
            i === 0 ? "w-full" : i === 1 ? "w-4/5" : "w-3/5"
          )}
        />
      ))}
    </div>
  );
}

function ErrorRow({ onRetry }: { onRetry?: () => void }) {
  return (
    <div className="flex items-center gap-2 py-1">
      <AlertTriangle className="h-3.5 w-3.5 text-destructive shrink-0" />
      <span className="text-xs text-destructive">Analysis failed.</span>
      {onRetry && (
        <Button
          variant="ghost"
          size="sm"
          onClick={onRetry}
          className="ml-auto h-7 gap-1 px-2 text-xs"
        >
          <RefreshCw className="h-3 w-3" />
          Retry
        </Button>
      )}
    </div>
  );
}

interface SectionCardProps {
  headerIcon: React.ReactNode;
  title: string;
  rightEl?: React.ReactNode;
  isPending: boolean;
  isError: boolean;
  onRetry?: () => void;
  skeletonRows?: number;
  children?: React.ReactNode;
  className?: string;
}

function SectionCard({
  headerIcon,
  title,
  rightEl,
  isPending,
  isError,
  onRetry,
  skeletonRows = 3,
  children,
  className,
}: SectionCardProps) {
  return (
    <div
      className={cn(
        "rounded-xl border border-border/60 bg-card/60 backdrop-blur-sm overflow-hidden flex flex-col",
        className
      )}
    >
      <div className="flex items-center gap-2.5 px-5 py-3.5 border-b border-border/40 bg-muted/20 shrink-0">
        {headerIcon}
        <h2 className="text-sm font-semibold text-foreground">{title}</h2>
        {rightEl && (
          <div className="ml-auto flex items-center gap-2">{rightEl}</div>
        )}
      </div>
      <div className="flex-1 p-5">
        {isPending && <SectionSkeleton rows={skeletonRows} />}
        {isError && !isPending && <ErrorRow onRetry={onRetry} />}
        {!isPending && !isError && children}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// KPI Pill
// ---------------------------------------------------------------------------

function KpiPill({
  label,
  value,
  icon: Icon,
  iconCls,
}: {
  label: string;
  value: React.ReactNode;
  icon: React.ElementType;
  iconCls: string;
}) {
  return (
    <div className="flex flex-1 items-center gap-3 min-w-[160px] rounded-xl border border-border/60 bg-card/60 px-4 py-3.5 backdrop-blur-sm">
      <div
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
          iconCls
        )}
      >
        <Icon className="h-4 w-4" />
      </div>
      <div className="min-w-0">
        <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
          {label}
        </p>
        <div className="text-sm font-semibold text-foreground">{value}</div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Status pulse
// ---------------------------------------------------------------------------

function StatusPulse({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="relative flex h-2 w-2">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75" />
        <span className="relative inline-flex rounded-full h-2 w-2 bg-primary" />
      </span>
      <span className="text-xs text-muted-foreground">{label}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section: Executive Summary
// ---------------------------------------------------------------------------

function ExecutiveSummary({ data }: { data: InsightResponse }) {
  return (
    <motion.div
      variants={stagger}
      initial="hidden"
      animate="show"
      className="space-y-4"
    >
      <motion.div
        variants={fadeIn}
        className="rounded-lg border border-primary/20 bg-primary/5 p-4 flex items-start gap-3"
      >
        <CheckCircle2 className="h-4 w-4 text-primary shrink-0 mt-0.5" />
        <p className="text-sm text-foreground leading-relaxed">{data.summary}</p>
      </motion.div>

      {data.recommendations.length > 0 && (
        <motion.div
          variants={fadeIn}
          className="grid grid-cols-1 gap-2 sm:grid-cols-2"
        >
          {data.recommendations.slice(0, 4).map((rec, i) => (
            <div
              key={i}
              className="flex items-start gap-2 rounded-lg bg-muted/30 px-3 py-2.5"
            >
              <span className="mt-0.5 h-4 w-4 shrink-0 flex items-center justify-center rounded-sm bg-amber-500/10">
                <Zap className="h-2.5 w-2.5 text-amber-500" />
              </span>
              <span className="text-xs text-foreground/80 leading-relaxed">
                {rec}
              </span>
            </div>
          ))}
        </motion.div>
      )}

      <div className="flex items-center justify-end gap-2 pt-1">
        {data.cache_hit && (
          <Badge variant="secondary" className="text-[10px]">
            cached
          </Badge>
        )}
        <span className="text-[10px] text-muted-foreground/60 tabular-nums">
          {data.generation_time_ms.toFixed(0)} ms
        </span>
      </div>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Section: Data Quality
// ---------------------------------------------------------------------------

function DataQuality({ data }: { data: AnomalyResponse }) {
  const sev = data.severity;
  const sevStyle = SEVERITY_STYLES[sev] ?? SEVERITY_STYLES.none;
  const isHealthy = data.total_anomaly_count === 0;

  return (
    <motion.div
      variants={stagger}
      initial="hidden"
      animate="show"
      className="space-y-4"
    >
      <motion.div
        variants={fadeIn}
        className={cn(
          "rounded-lg border p-3.5 flex items-center gap-3",
          sevStyle.cardBorder
        )}
      >
        {isHealthy ? (
          <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
        ) : (
          <AlertTriangle
            className={cn(
              "h-4 w-4 shrink-0",
              sev === "critical"
                ? "text-red-500"
                : sev === "high"
                ? "text-orange-500"
                : "text-amber-500"
            )}
          />
        )}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-foreground">
            {isHealthy
              ? "No anomalies detected"
              : `${data.total_anomaly_count} anomalies detected`}
          </p>
          <p className="text-xs text-muted-foreground mt-0.5">
            {isHealthy
              ? "All numeric columns appear clean"
              : `Across ${data.affected_metrics.length} column(s)`}
          </p>
        </div>
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium shrink-0",
            sevStyle.pill
          )}
        >
          <span className={cn("h-1.5 w-1.5 rounded-full", sevStyle.dot)} />
          {sevStyle.label}
        </span>
      </motion.div>

      {data.affected_metrics.length > 0 && (
        <motion.div variants={fadeIn}>
          <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground mb-2">
            Affected Columns
          </p>
          <div className="flex flex-wrap gap-1.5">
            {data.affected_metrics.map((col) => (
              <Badge key={col} variant="muted" className="font-mono text-[10px]">
                {col}
              </Badge>
            ))}
          </div>
        </motion.div>
      )}

      {data.possible_reasons.length > 0 && (
        <motion.div variants={fadeIn}>
          <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground mb-2">
            Possible Causes
          </p>
          <ul className="space-y-1.5">
            {data.possible_reasons.map((r, i) => (
              <li
                key={i}
                className="flex items-start gap-2 text-xs text-muted-foreground"
              >
                <span className="mt-1.5 h-1 w-1 rounded-full bg-muted-foreground/50 shrink-0" />
                {r}
              </li>
            ))}
          </ul>
        </motion.div>
      )}

      <div className="flex items-center justify-end gap-2">
        {data.cache_hit && (
          <Badge variant="secondary" className="text-[10px]">
            cached
          </Badge>
        )}
        <span className="text-[10px] text-muted-foreground/60 tabular-nums">
          {(data.detection_time_ms / 1000).toFixed(2)}s
        </span>
      </div>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Section: Anomaly Detection
// ---------------------------------------------------------------------------

function AnomalyDetection({ data }: { data: AnomalyResponse }) {
  return (
    <motion.div
      variants={stagger}
      initial="hidden"
      animate="show"
      className="space-y-4"
    >
      {data.chart_spec && (
        <motion.div
          variants={fadeIn}
          className="rounded-lg border border-border/40 overflow-hidden"
        >
          <div className="flex items-center gap-2 px-3 py-2 border-b border-border/40 bg-muted/20">
            <Database className="h-3 w-3 text-muted-foreground" />
            <span className="text-[10px] font-medium text-muted-foreground">
              Anomaly Chart
            </span>
          </div>
          <div className="px-2 pb-2 pt-1">
            <PlotlyChart spec={data.chart_spec} />
          </div>
        </motion.div>
      )}

      {data.anomalies.length > 0 ? (
        <motion.div variants={fadeIn} className="space-y-2">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            Affected Columns
          </p>
          {data.anomalies.slice(0, 6).map((ca) => {
            const worst =
              ca.anomaly_points.length > 0
                ? ca.anomaly_points.reduce((b, p) =>
                    p.score > b.score ? p : b
                  )
                : null;
            const sev = worst?.severity ?? "low";
            const s = SEVERITY_STYLES[sev] ?? SEVERITY_STYLES.low;
            return (
              <div
                key={ca.column}
                className="flex items-center justify-between rounded-lg border border-border/40 bg-muted/20 px-3 py-2.5"
              >
                <span className="font-mono text-xs text-foreground">
                  {ca.column}
                </span>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-[10px] tabular-nums text-muted-foreground">
                    {ca.anomaly_count} pts
                  </span>
                  <span
                    className={cn(
                      "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px]",
                      s.pill
                    )}
                  >
                    <span className={cn("h-1 w-1 rounded-full", s.dot)} />
                    {s.label}
                  </span>
                </div>
              </div>
            );
          })}
          {data.anomalies.length > 6 && (
            <p className="text-xs text-muted-foreground/60 text-center pt-1">
              +{data.anomalies.length - 6} more columns
            </p>
          )}
        </motion.div>
      ) : (
        <div className="flex flex-col items-center gap-2 py-6 text-center">
          <CheckCircle2 className="h-8 w-8 text-emerald-500/50" />
          <p className="text-xs text-muted-foreground">
            No column-level anomalies found
          </p>
        </div>
      )}
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Section: Key Insights & Trends
// ---------------------------------------------------------------------------

function InsightsSection({ data }: { data: InsightResponse }) {
  return (
    <motion.div
      variants={stagger}
      initial="hidden"
      animate="show"
      className="space-y-5"
    >
      {data.key_insights.length > 0 && (
        <motion.div variants={fadeIn}>
          <div className="flex items-center gap-2 mb-2.5">
            <Lightbulb className="h-3.5 w-3.5 text-primary" />
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Key Insights
            </p>
            <span className="text-[10px] text-muted-foreground/60">
              ({data.key_insights.length})
            </span>
          </div>
          <motion.ul variants={stagger} className="space-y-2.5">
            {data.key_insights.map((text, i) => (
              <motion.li
                key={i}
                variants={fadeIn}
                className="flex items-start gap-3"
              >
                <span className="shrink-0 flex h-5 w-5 items-center justify-center rounded-full bg-primary/10 text-[10px] font-semibold text-primary">
                  {i + 1}
                </span>
                <span className="text-sm text-foreground/85 leading-relaxed">
                  {text}
                </span>
              </motion.li>
            ))}
          </motion.ul>
        </motion.div>
      )}

      {data.trends.length > 0 && (
        <motion.div variants={fadeIn}>
          <div className="flex items-center gap-2 mb-2.5">
            <TrendingUp className="h-3.5 w-3.5 text-primary" />
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Trends
            </p>
          </div>
          <ul className="space-y-2">
            {data.trends.map((text, i) => (
              <li key={i} className="flex items-start gap-2.5">
                <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-primary/50 shrink-0" />
                <span className="text-sm text-foreground/80 leading-relaxed">
                  {text}
                </span>
              </li>
            ))}
          </ul>
        </motion.div>
      )}
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Section: Root Cause Analysis
// ---------------------------------------------------------------------------

function RootCauseSection({ data }: { data: RootCauseResponse }) {
  const changePos = data.total_change_pct >= 0;
  const formatPct = (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;

  return (
    <motion.div
      variants={stagger}
      initial="hidden"
      animate="show"
      className="space-y-4"
    >
      <motion.div
        variants={fadeIn}
        className={cn(
          "rounded-lg border p-3.5 flex items-start gap-3",
          changePos
            ? "border-emerald-500/20 bg-emerald-500/5"
            : "border-red-500/20 bg-red-500/5"
        )}
      >
        <Search
          className={cn(
            "h-4 w-4 shrink-0 mt-0.5",
            changePos ? "text-emerald-500" : "text-red-500"
          )}
        />
        <div className="space-y-1 flex-1 min-w-0">
          <p className="text-sm font-medium text-foreground leading-snug">
            {data.problem}
          </p>
          <div className="flex gap-3 text-[10px] text-muted-foreground font-mono">
            {data.metric_column && (
              <span>
                metric:{" "}
                <strong className="text-foreground">{data.metric_column}</strong>
              </span>
            )}
            <span
              className={cn(
                "font-semibold",
                changePos ? "text-emerald-600 dark:text-emerald-400" : "text-red-500"
              )}
            >
              {formatPct(data.total_change_pct)}
            </span>
          </div>
        </div>
      </motion.div>

      {data.root_causes.length > 0 && (
        <motion.div variants={fadeIn} className="space-y-2">
          <div className="flex items-center gap-2">
            <GitBranch className="h-3.5 w-3.5 text-muted-foreground" />
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Root Causes
            </p>
          </div>
          {data.root_causes.slice(0, 5).map((rc) => (
            <div
              key={`${rc.dimension}-${rc.value}`}
              className="rounded-lg border border-border/40 bg-muted/20 p-3 space-y-1"
            >
              <div className="flex items-center justify-between gap-2">
                <p className="text-xs font-medium text-foreground truncate">
                  <span className="text-muted-foreground font-normal">
                    {rc.dimension}:{" "}
                  </span>
                  {rc.value}
                </p>
                <div className="flex items-center gap-1.5 shrink-0">
                  <span
                    className={cn(
                      "rounded-full px-2 py-0.5 text-[10px]",
                      IMPACT_STYLES[rc.impact_level] ?? IMPACT_STYLES.low
                    )}
                  >
                    {rc.impact_level}
                  </span>
                  <span className="text-[10px] tabular-nums text-muted-foreground font-mono">
                    {formatPct(rc.contribution_pct)}
                  </span>
                </div>
              </div>
              <p className="text-[10px] text-muted-foreground leading-relaxed">
                {rc.description}
              </p>
            </div>
          ))}
        </motion.div>
      )}

      <div className="flex items-center justify-end gap-2">
        {data.cache_hit && (
          <Badge variant="secondary" className="text-[10px]">
            cached
          </Badge>
        )}
        <span className="text-[10px] text-muted-foreground/60 tabular-nums">
          {data.analysis_time_ms.toFixed(0)} ms
        </span>
      </div>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Section: Recommendations
// ---------------------------------------------------------------------------

function RecommendationsSection({ data }: { data: RecommendationResponse }) {
  const priorities: RecommendationPriority[] = [
    "critical",
    "high",
    "medium",
    "low",
  ];

  return (
    <motion.div
      variants={stagger}
      initial="hidden"
      animate="show"
      className="space-y-5"
    >
      <motion.div
        variants={fadeIn}
        className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border/40 bg-muted/20 px-4 py-2.5"
      >
        <p className="text-xs text-muted-foreground max-w-xl">{data.summary}</p>
        <div className="flex flex-wrap items-center gap-1.5">
          {priorities
            .filter((p) => data.recommendations.some((r) => r.priority === p))
            .map((p) => {
              const count = data.recommendations.filter(
                (r) => r.priority === p
              ).length;
              const cfg = PRIORITY_CONFIG[p];
              return (
                <span
                  key={p}
                  className={cn(
                    "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
                    cfg.cls
                  )}
                >
                  <span className={cn("h-1.5 w-1.5 rounded-full", cfg.dot)} />
                  {cfg.label} · {count}
                </span>
              );
            })}
          {data.llm_enhanced && (
            <Badge variant="secondary" className="gap-1 text-[10px]">
              <Sparkles className="h-2.5 w-2.5" />
              LLM
            </Badge>
          )}
        </div>
      </motion.div>

      {priorities.map((p) => {
        const recs = data.recommendations.filter((r) => r.priority === p);
        if (recs.length === 0) return null;
        const cfg = PRIORITY_CONFIG[p];
        return (
          <motion.div key={p} variants={fadeIn} className="space-y-2.5">
            <div className="flex items-center gap-2">
              <span className={cn("h-1.5 w-1.5 rounded-full", cfg.dot)} />
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {cfg.label}
              </p>
            </div>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              {recs.map((rec, i) => (
                <div
                  key={i}
                  className="rounded-lg border border-border/40 bg-card/60 p-3.5 space-y-2"
                >
                  <p className="text-sm font-medium text-foreground leading-snug">
                    {rec.action}
                  </p>
                  <div className="flex items-center gap-2">
                    <div className="flex-1 h-1 bg-muted rounded-full overflow-hidden">
                      <div
                        className="h-full bg-primary/70 rounded-full"
                        style={{
                          width: `${Math.round(rec.confidence * 100)}%`,
                        }}
                      />
                    </div>
                    <span className="text-[10px] text-muted-foreground tabular-nums">
                      {Math.round(rec.confidence * 100)}%
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground leading-relaxed">
                    {rec.reason}
                  </p>
                  {rec.expected_impact && (
                    <p className="text-[10px] text-foreground/70 bg-muted/30 rounded px-2 py-1">
                      Impact: {rec.expected_impact}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </motion.div>
        );
      })}

      <div className="flex items-center justify-end gap-2 pt-1">
        {data.cache_hit && (
          <Badge variant="secondary" className="text-[10px]">
            cached
          </Badge>
        )}
        <span className="text-[10px] text-muted-foreground/60">
          {data.generation_time_ms.toFixed(0)} ms
        </span>
      </div>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Main workspace
// ---------------------------------------------------------------------------

interface AnalysisWorkspaceProps {
  datasetId: string;
}

export function AnalysisWorkspace({ datasetId }: AnalysisWorkspaceProps) {
  const preview = useDatasetPreview(datasetId);

  const recsMutation = useMutation({
    mutationFn: (anomalies: AnomalyResponse | null) =>
      generateRecommendations({ dataset_id: datasetId, anomalies }),
  });

  const anomaliesMutation = useMutation({
    mutationFn: () => detectAnomalies({ dataset_id: datasetId }),
    onSuccess: (data) => recsMutation.mutate(data),
    onError: () => recsMutation.mutate(null),
  });

  const insightsMutation = useMutation({
    mutationFn: () =>
      generateInsights({
        dataset_id: datasetId,
        question:
          "What are the key insights, trends, and patterns in this dataset?",
      }),
  });

  const rootCauseMutation = useMutation({
    mutationFn: () =>
      analyzeRootCause({
        dataset_id: datasetId,
        question:
          "Why did the main metric change? Analyze all key dimensions and segment contributions.",
      }),
  });

  // Fire all analyses on mount — no user interaction required
  useEffect(() => {
    insightsMutation.mutate();
    anomaliesMutation.mutate();
    rootCauseMutation.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const anyPending =
    insightsMutation.isPending ||
    anomaliesMutation.isPending ||
    rootCauseMutation.isPending ||
    recsMutation.isPending;

  const anomalySev = anomaliesMutation.data?.severity ?? "none";
  const insightsCount = insightsMutation.data?.key_insights.length ?? 0;
  const filename = preview.data?.filename ?? datasetId;

  const recsIsPending = anomaliesMutation.isPending || recsMutation.isPending;
  const recsIsError =
    (!anomaliesMutation.isPending && anomaliesMutation.isError && !anomaliesMutation.data) ||
    recsMutation.isError;

  return (
    <div className="flex flex-col h-full bg-background">
      {/* ── Header ──────────────────────────────────────────────────── */}
      <header className="flex h-11 shrink-0 items-center justify-between border-b border-border/40 bg-background/95 backdrop-blur-sm px-4">
        <div className="flex items-center gap-2 min-w-0">
          <Link
            href={`/datasets/${datasetId}`}
            aria-label="Back to dataset"
            className="flex h-7 w-7 items-center justify-center rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          </Link>
          <div className="h-4 w-px bg-border/60 mx-1 shrink-0" />
          <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-primary/10">
            <BarChart2 className="h-3 w-3 text-primary" />
          </div>
          <span className="ml-1.5 text-sm font-medium text-foreground">
            Autonomous Analysis
          </span>
          {preview.data && (
            <>
              <span className="text-muted-foreground/40 mx-1.5">·</span>
              <span className="text-sm text-muted-foreground truncate max-w-[200px]">
                {filename}
              </span>
            </>
          )}
        </div>
        <div className="shrink-0">
          {anyPending ? (
            <StatusPulse label="Auto-analyzing…" />
          ) : (
            <span className="flex items-center gap-1.5 text-xs text-emerald-500">
              <CheckCircle2 className="h-3.5 w-3.5" />
              Analysis complete
            </span>
          )}
        </div>
      </header>

      {/* ── Scrollable body ──────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-6xl mx-auto px-5 py-6 space-y-5">
          {/* KPI row */}
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2 }}
            className="flex flex-wrap gap-3"
          >
            <KpiPill
              label="Rows"
              value={
                preview.data ? (
                  preview.data.rows.toLocaleString()
                ) : (
                  <Skeleton className="h-4 w-16" />
                )
              }
              icon={Rows3}
              iconCls="bg-primary/10 text-primary"
            />
            <KpiPill
              label="Columns"
              value={
                preview.data ? (
                  String(preview.data.columns)
                ) : (
                  <Skeleton className="h-4 w-8" />
                )
              }
              icon={Layers}
              iconCls="bg-violet-500/10 text-violet-500"
            />
            <KpiPill
              label="Anomaly Severity"
              value={
                anomaliesMutation.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                ) : anomaliesMutation.isError ? (
                  <span className="text-destructive text-xs">Failed</span>
                ) : (
                  <span
                    className={cn(
                      "inline-flex items-center gap-1.5",
                      SEVERITY_STYLES[anomalySev]?.pill
                    )}
                  >
                    <span
                      className={cn(
                        "h-1.5 w-1.5 rounded-full",
                        SEVERITY_STYLES[anomalySev]?.dot
                      )}
                    />
                    {SEVERITY_STYLES[anomalySev]?.label}
                  </span>
                )
              }
              icon={AlertTriangle}
              iconCls="bg-orange-500/10 text-orange-500"
            />
            <KpiPill
              label="Insights Found"
              value={
                insightsMutation.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                ) : insightsMutation.isError ? (
                  <span className="text-destructive text-xs">Failed</span>
                ) : (
                  String(insightsCount)
                )
              }
              icon={Sparkles}
              iconCls="bg-primary/10 text-primary"
            />
          </motion.div>

          {/* ── Executive Summary ─────────────────────────────────── */}
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.22, delay: 0.04 }}
          >
            <SectionCard
              headerIcon={
                <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-primary/10">
                  <CheckCircle2 className="h-3.5 w-3.5 text-primary" />
                </div>
              }
              title="Executive Summary"
              rightEl={
                insightsMutation.data && (
                  <span className="text-xs text-muted-foreground tabular-nums">
                    {insightsMutation.data.key_insights.length} insights ·{" "}
                    {insightsMutation.data.trends.length} trends
                  </span>
                )
              }
              isPending={insightsMutation.isPending}
              isError={insightsMutation.isError}
              onRetry={() => insightsMutation.mutate()}
              skeletonRows={4}
            >
              {insightsMutation.data && (
                <ExecutiveSummary data={insightsMutation.data} />
              )}
            </SectionCard>
          </motion.div>

          {/* ── Data Quality + Anomaly Detection ──────────────────── */}
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.22, delay: 0.08 }}
            className="grid grid-cols-1 gap-5 lg:grid-cols-2"
          >
            <SectionCard
              headerIcon={
                <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-emerald-500/10">
                  <Database className="h-3.5 w-3.5 text-emerald-500" />
                </div>
              }
              title="Data Quality"
              rightEl={
                anomaliesMutation.data && (
                  <span
                    className={cn(
                      "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px]",
                      SEVERITY_STYLES[anomalySev]?.pill
                    )}
                  >
                    <span
                      className={cn(
                        "h-1 w-1 rounded-full",
                        SEVERITY_STYLES[anomalySev]?.dot
                      )}
                    />
                    {SEVERITY_STYLES[anomalySev]?.label}
                  </span>
                )
              }
              isPending={anomaliesMutation.isPending}
              isError={anomaliesMutation.isError}
              onRetry={() => anomaliesMutation.mutate()}
              skeletonRows={5}
            >
              {anomaliesMutation.data && (
                <DataQuality data={anomaliesMutation.data} />
              )}
            </SectionCard>

            <SectionCard
              headerIcon={
                <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-orange-500/10">
                  <AlertTriangle className="h-3.5 w-3.5 text-orange-500" />
                </div>
              }
              title="Anomaly Detection"
              rightEl={
                anomaliesMutation.data && (
                  <span className="text-xs text-muted-foreground tabular-nums">
                    {anomaliesMutation.data.total_anomaly_count} anomalies ·{" "}
                    {anomaliesMutation.data.anomalies.length} col(s)
                  </span>
                )
              }
              isPending={anomaliesMutation.isPending}
              isError={anomaliesMutation.isError}
              onRetry={() => anomaliesMutation.mutate()}
              skeletonRows={5}
            >
              {anomaliesMutation.data && (
                <AnomalyDetection data={anomaliesMutation.data} />
              )}
            </SectionCard>
          </motion.div>

          {/* ── Key Insights + Root Cause ──────────────────────────── */}
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.22, delay: 0.12 }}
            className="grid grid-cols-1 gap-5 lg:grid-cols-2"
          >
            <SectionCard
              headerIcon={
                <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-primary/10">
                  <Sparkles className="h-3.5 w-3.5 text-primary" />
                </div>
              }
              title="Key Insights & Trends"
              rightEl={
                insightsMutation.data && (
                  <span className="text-xs text-muted-foreground tabular-nums">
                    {insightsMutation.data.key_insights.length +
                      insightsMutation.data.trends.length}{" "}
                    items
                  </span>
                )
              }
              isPending={insightsMutation.isPending}
              isError={insightsMutation.isError}
              onRetry={() => insightsMutation.mutate()}
              skeletonRows={6}
            >
              {insightsMutation.data && (
                <InsightsSection data={insightsMutation.data} />
              )}
            </SectionCard>

            <SectionCard
              headerIcon={
                <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-violet-500/10">
                  <GitBranch className="h-3.5 w-3.5 text-violet-500" />
                </div>
              }
              title="Root Cause Analysis"
              rightEl={
                rootCauseMutation.data && (
                  <span className="text-xs text-muted-foreground tabular-nums">
                    {rootCauseMutation.data.root_causes.length} cause(s)
                  </span>
                )
              }
              isPending={rootCauseMutation.isPending}
              isError={rootCauseMutation.isError}
              onRetry={() => rootCauseMutation.mutate()}
              skeletonRows={5}
            >
              {rootCauseMutation.data && (
                <RootCauseSection data={rootCauseMutation.data} />
              )}
            </SectionCard>
          </motion.div>

          {/* ── Recommendations ───────────────────────────────────── */}
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.22, delay: 0.16 }}
          >
            <SectionCard
              headerIcon={
                <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-amber-500/10">
                  <Lightbulb className="h-3.5 w-3.5 text-amber-500" />
                </div>
              }
              title="Recommendations"
              rightEl={
                recsMutation.data && (
                  <span className="text-xs text-muted-foreground tabular-nums">
                    {recsMutation.data.total_count} action(s)
                  </span>
                )
              }
              isPending={recsIsPending}
              isError={recsIsError}
              onRetry={() =>
                recsMutation.mutate(anomaliesMutation.data ?? null)
              }
              skeletonRows={4}
            >
              {recsMutation.data && (
                <RecommendationsSection data={recsMutation.data} />
              )}
            </SectionCard>
          </motion.div>
        </div>
      </div>
    </div>
  );
}
