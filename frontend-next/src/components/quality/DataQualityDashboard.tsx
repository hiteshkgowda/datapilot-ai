"use client";

import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import type { Variants } from "framer-motion";
import {
  AlertTriangle,
  BadgeCheck,
  CheckCircle2,
  Database,
  FileSearch,
  Layers,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  TrendingDown,
  XCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { PlotlyChart } from "@/components/ask/PlotlyChart";
import { getDataQuality } from "@/lib/api/data-quality";
import type {
  ColumnQuality,
  DataQualityRecommendation,
  DataQualityResponse,
  QualityGrade,
  QualityPriority,
} from "@/lib/api/types";

// ─── Animation ────────────────────────────────────────────────────────────────

const fadeUp: Variants = {
  hidden: { opacity: 0, y: 14 },
  show: { opacity: 1, y: 0, transition: { duration: 0.22 } },
};

const stagger: Variants = {
  show: { transition: { staggerChildren: 0.07 } },
};

// ─── Grade helpers ────────────────────────────────────────────────────────────

const GRADE_CONFIG: Record<
  QualityGrade,
  { color: string; ring: string; bg: string; label: string }
> = {
  A: {
    color: "text-emerald-400",
    ring: "ring-emerald-500/40",
    bg: "bg-emerald-500/10",
    label: "Excellent",
  },
  B: {
    color: "text-sky-400",
    ring: "ring-sky-500/40",
    bg: "bg-sky-500/10",
    label: "Good",
  },
  C: {
    color: "text-amber-400",
    ring: "ring-amber-500/40",
    bg: "bg-amber-500/10",
    label: "Fair",
  },
  D: {
    color: "text-orange-400",
    ring: "ring-orange-500/40",
    bg: "bg-orange-500/10",
    label: "Poor",
  },
  F: {
    color: "text-red-400",
    ring: "ring-red-500/40",
    bg: "bg-red-500/10",
    label: "Critical",
  },
};

const PRIORITY_CONFIG: Record<
  QualityPriority,
  { color: string; bg: string; dot: string; label: string }
> = {
  critical: {
    color: "text-red-400",
    bg: "bg-red-500/10 border-red-500/20",
    dot: "bg-red-500",
    label: "Critical",
  },
  high: {
    color: "text-orange-400",
    bg: "bg-orange-500/10 border-orange-500/20",
    dot: "bg-orange-500",
    label: "High",
  },
  medium: {
    color: "text-amber-400",
    bg: "bg-amber-500/10 border-amber-500/20",
    dot: "bg-amber-500",
    label: "Medium",
  },
  low: {
    color: "text-sky-400",
    bg: "bg-sky-500/10 border-sky-500/20",
    dot: "bg-sky-500",
    label: "Low",
  },
};

function healthColor(score: number) {
  if (score >= 85) return "text-emerald-400";
  if (score >= 70) return "text-sky-400";
  if (score >= 50) return "text-amber-400";
  return "text-red-400";
}

function healthBarColor(score: number) {
  if (score >= 85) return "bg-emerald-500";
  if (score >= 70) return "bg-sky-500";
  if (score >= 50) return "bg-amber-500";
  return "bg-red-500";
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function ScoreRing({ score, grade }: { score: number; grade: QualityGrade }) {
  const cfg = GRADE_CONFIG[grade];
  const radius = 52;
  const circ = 2 * Math.PI * radius;
  const dash = (score / 100) * circ;

  return (
    <div className="flex flex-col items-center gap-3">
      <div className="relative flex items-center justify-center">
        <svg width="136" height="136" className="-rotate-90">
          <circle
            cx="68"
            cy="68"
            r={radius}
            fill="none"
            stroke="hsl(var(--border) / 0.4)"
            strokeWidth="10"
          />
          <circle
            cx="68"
            cy="68"
            r={radius}
            fill="none"
            stroke="hsl(var(--primary))"
            strokeWidth="10"
            strokeDasharray={`${dash} ${circ}`}
            strokeLinecap="round"
            className="transition-all duration-700"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={cn("text-4xl font-bold tabular-nums", cfg.color)}>
            {grade}
          </span>
          <span className="text-xs text-muted-foreground mt-0.5">
            {score.toFixed(0)}/100
          </span>
        </div>
      </div>
      <span className={cn("text-sm font-semibold", cfg.color)}>{cfg.label}</span>
    </div>
  );
}

function DimensionBar({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: number;
  icon: React.ElementType;
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Icon className="h-3.5 w-3.5 shrink-0" />
          {label}
        </div>
        <span className={cn("text-xs font-semibold tabular-nums", healthColor(value))}>
          {value.toFixed(1)}%
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-muted/50 overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all duration-500", healthBarColor(value))}
          style={{ width: `${value}%` }}
        />
      </div>
    </div>
  );
}

function StatPill({
  label,
  value,
  sub,
  variant = "default",
}: {
  label: string;
  value: string;
  sub?: string;
  variant?: "default" | "warn" | "danger" | "good";
}) {
  const valueColor =
    variant === "danger"
      ? "text-red-400"
      : variant === "warn"
      ? "text-amber-400"
      : variant === "good"
      ? "text-emerald-400"
      : "text-foreground";

  return (
    <div className="flex flex-col gap-1 rounded-xl border border-border/60 bg-card/60 px-4 py-3">
      <span className="text-[11px] text-muted-foreground uppercase tracking-wider">
        {label}
      </span>
      <span className={cn("text-xl font-bold tabular-nums", valueColor)}>{value}</span>
      {sub && <span className="text-[10px] text-muted-foreground/60">{sub}</span>}
    </div>
  );
}

function RecommendationCard({ rec }: { rec: DataQualityRecommendation }) {
  const cfg = PRIORITY_CONFIG[rec.priority];
  return (
    <div className={cn("rounded-xl border p-4 space-y-2", cfg.bg)}>
      <div className="flex items-start gap-2.5">
        <div
          className={cn(
            "mt-1 h-2 w-2 rounded-full shrink-0",
            cfg.dot
          )}
        />
        <div className="space-y-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={cn("text-xs font-semibold uppercase tracking-wide", cfg.color)}>
              {cfg.label}
            </span>
          </div>
          <p className="text-sm font-medium text-foreground">{rec.issue}</p>
          <p className="text-sm text-muted-foreground">{rec.action}</p>
          {rec.affected_columns.length > 0 && (
            <div className="flex flex-wrap gap-1 pt-0.5">
              {rec.affected_columns.slice(0, 6).map((col) => (
                <span
                  key={col}
                  className="inline-flex items-center rounded-md bg-muted/50 px-2 py-0.5 text-[10px] font-mono text-muted-foreground"
                >
                  {col}
                </span>
              ))}
              {rec.affected_columns.length > 6 && (
                <span className="text-[10px] text-muted-foreground self-center">
                  +{rec.affected_columns.length - 6} more
                </span>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ColumnHealthTable({ columns }: { columns: ColumnQuality[] }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-border/60">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border/60 bg-muted/20">
            <th className="text-left px-4 py-2.5 text-xs font-medium text-muted-foreground">Column</th>
            <th className="text-left px-4 py-2.5 text-xs font-medium text-muted-foreground">Type</th>
            <th className="px-4 py-2.5 text-xs font-medium text-muted-foreground text-right">Health</th>
            <th className="px-4 py-2.5 text-xs font-medium text-muted-foreground text-right">Missing</th>
            <th className="px-4 py-2.5 text-xs font-medium text-muted-foreground text-right">Unique</th>
            <th className="px-4 py-2.5 text-xs font-medium text-muted-foreground text-right">Outliers</th>
            <th className="px-4 py-2.5 text-xs font-medium text-muted-foreground">Issues</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border/40">
          {columns.map((col) => (
            <tr
              key={col.name}
              className="hover:bg-muted/10 transition-colors"
            >
              <td className="px-4 py-2.5 font-mono text-xs text-foreground font-medium truncate max-w-[140px]">
                {col.name}
              </td>
              <td className="px-4 py-2.5">
                <span className="inline-flex items-center rounded-md bg-muted/50 px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground">
                  {col.dtype}
                </span>
              </td>
              <td className="px-4 py-2.5 text-right">
                <div className="inline-flex items-center gap-2">
                  <div className="w-16 h-1.5 rounded-full bg-muted/50 overflow-hidden">
                    <div
                      className={cn("h-full rounded-full", healthBarColor(col.health_score))}
                      style={{ width: `${col.health_score}%` }}
                    />
                  </div>
                  <span className={cn("text-xs font-semibold tabular-nums w-10 text-right", healthColor(col.health_score))}>
                    {col.health_score.toFixed(0)}
                  </span>
                </div>
              </td>
              <td className="px-4 py-2.5 text-right">
                <span className={cn(
                  "text-xs tabular-nums",
                  col.missing_pct >= 30 ? "text-red-400 font-semibold" :
                  col.missing_pct >= 5 ? "text-amber-400 font-medium" :
                  "text-muted-foreground"
                )}>
                  {col.missing_pct > 0 ? `${col.missing_pct.toFixed(1)}%` : "—"}
                </span>
              </td>
              <td className="px-4 py-2.5 text-right">
                <span className="text-xs text-muted-foreground tabular-nums">
                  {col.unique_pct.toFixed(1)}%
                </span>
              </td>
              <td className="px-4 py-2.5 text-right">
                <span className={cn(
                  "text-xs tabular-nums",
                  col.outlier_pct >= 15 ? "text-red-400 font-semibold" :
                  col.outlier_pct >= 5 ? "text-amber-400 font-medium" :
                  "text-muted-foreground"
                )}>
                  {col.outlier_count > 0 ? `${col.outlier_count} (${col.outlier_pct.toFixed(1)}%)` : "—"}
                </span>
              </td>
              <td className="px-4 py-2.5">
                {col.issues.length > 0 ? (
                  <div className="flex flex-wrap gap-1">
                    {col.issues.slice(0, 2).map((issue, i) => (
                      <span
                        key={i}
                        className="inline-flex items-center gap-1 rounded-md bg-amber-500/10 border border-amber-500/20 px-1.5 py-0.5 text-[10px] text-amber-400"
                      >
                        <AlertTriangle className="h-2.5 w-2.5 shrink-0" />
                        {issue.length > 32 ? issue.slice(0, 32) + "…" : issue}
                      </span>
                    ))}
                  </div>
                ) : (
                  <span className="inline-flex items-center gap-1 text-[10px] text-emerald-400">
                    <CheckCircle2 className="h-3 w-3" /> Clean
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── Loading skeleton ─────────────────────────────────────────────────────────

function LoadingSkeleton() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Skeleton className="h-10 w-10 rounded-xl" />
        <div className="space-y-1.5">
          <Skeleton className="h-5 w-48" />
          <Skeleton className="h-3.5 w-32" />
        </div>
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <Skeleton key={i} className="h-24 rounded-xl" />
        ))}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Skeleton className="h-64 rounded-xl" />
        <Skeleton className="col-span-2 h-64 rounded-xl" />
      </div>
      <Skeleton className="h-80 rounded-xl" />
    </div>
  );
}

// ─── Section wrapper ──────────────────────────────────────────────────────────

function Section({
  title,
  icon: Icon,
  children,
  className,
}: {
  title: string;
  icon: React.ElementType;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <motion.div variants={fadeUp} className={cn("space-y-4", className)}>
      <div className="flex items-center gap-2">
        <Icon className="h-4 w-4 text-primary/70 shrink-0" />
        <h2 className="text-sm font-semibold text-foreground">{title}</h2>
      </div>
      {children}
    </motion.div>
  );
}

// ─── Main dashboard ───────────────────────────────────────────────────────────

interface DataQualityDashboardProps {
  datasetId: string;
}

export function DataQualityDashboard({ datasetId }: DataQualityDashboardProps) {
  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["data-quality", datasetId],
    queryFn: () => getDataQuality(datasetId),
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });

  if (isLoading) {
    return (
      <div className="max-w-6xl mx-auto px-6 py-8">
        <LoadingSkeleton />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4 py-24">
        <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-red-500/10">
          <XCircle className="h-6 w-6 text-red-400" />
        </div>
        <div className="text-center space-y-1">
          <p className="text-sm font-medium text-foreground">Analysis failed</p>
          <p className="text-sm text-muted-foreground">
            {(error as Error)?.message ?? "Something went wrong"}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => refetch()}>
          <RefreshCw className="mr-2 h-3.5 w-3.5" />
          Retry
        </Button>
      </div>
    );
  }

  if (!data) return null;

  const cfg = GRADE_CONFIG[data.grade];
  const dupVariant =
    data.duplicates.duplicate_pct >= 10
      ? "danger"
      : data.duplicates.duplicate_pct >= 1
      ? "warn"
      : "good";
  const missingVariant =
    data.missing_summary.total_missing_pct >= 30
      ? "danger"
      : data.missing_summary.total_missing_pct >= 5
      ? "warn"
      : "good";
  const outlierVariant =
    data.outlier_summary.total_outlier_count > 0 ? "warn" : "good";

  return (
    <motion.div
      variants={stagger}
      initial="hidden"
      animate="show"
      className="max-w-6xl mx-auto px-6 py-8 space-y-8"
    >
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <motion.div variants={fadeUp} className="flex items-start justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <div className={cn("flex h-10 w-10 items-center justify-center rounded-xl", cfg.bg)}>
            <ShieldCheck className={cn("h-5 w-5", cfg.color)} />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-foreground">Data Quality</h1>
            <p className="text-sm text-muted-foreground">
              {data.row_count.toLocaleString()} rows · {data.column_count} columns ·{" "}
              {data.analysis_time_ms.toFixed(0)} ms
              {data.cache_hit && (
                <span className="ml-2 text-[10px] uppercase tracking-wide text-primary/60">
                  cached
                </span>
              )}
            </p>
          </div>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => refetch()}
          disabled={isFetching}
        >
          <RefreshCw className={cn("mr-2 h-3.5 w-3.5", isFetching && "animate-spin")} />
          Refresh
        </Button>
      </motion.div>

      {/* ── Score + dimensions ─────────────────────────────────────────── */}
      <motion.div
        variants={fadeUp}
        className="grid grid-cols-1 lg:grid-cols-3 gap-6"
      >
        {/* Score ring */}
        <div className="flex flex-col items-center justify-center rounded-2xl border border-border/60 bg-card/70 py-8 px-4 gap-6">
          <ScoreRing score={data.overall_score} grade={data.grade} />
          <div className="w-full text-center space-y-1">
            <p className="text-xs text-muted-foreground">Overall Quality Score</p>
          </div>
        </div>

        {/* Dimensions */}
        <div className="col-span-2 rounded-2xl border border-border/60 bg-card/70 p-6 space-y-5">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Quality Dimensions
          </p>
          <DimensionBar
            label="Completeness"
            value={data.dimensions.completeness}
            icon={Database}
          />
          <DimensionBar
            label="Uniqueness"
            value={data.dimensions.uniqueness}
            icon={Layers}
          />
          <DimensionBar
            label="Validity"
            value={data.dimensions.validity}
            icon={ShieldCheck}
          />
          <DimensionBar
            label="Consistency"
            value={data.dimensions.consistency}
            icon={BadgeCheck}
          />
        </div>
      </motion.div>

      {/* ── KPI row ────────────────────────────────────────────────────── */}
      <motion.div
        variants={fadeUp}
        className="grid grid-cols-2 sm:grid-cols-4 gap-4"
      >
        <StatPill
          label="Duplicate Rows"
          value={data.duplicates.duplicate_row_count.toLocaleString()}
          sub={`${data.duplicates.duplicate_pct.toFixed(2)}% of dataset`}
          variant={dupVariant}
        />
        <StatPill
          label="Missing Cells"
          value={data.missing_summary.total_missing.toLocaleString()}
          sub={`${data.missing_summary.total_missing_pct.toFixed(2)}% of all cells`}
          variant={missingVariant}
        />
        <StatPill
          label="Total Outliers"
          value={data.outlier_summary.total_outlier_count.toLocaleString()}
          sub={`across ${data.outlier_summary.columns_with_outliers} column(s)`}
          variant={outlierVariant}
        />
        <StatPill
          label="Clean Columns"
          value={String(data.columns.filter((c) => c.issues.length === 0).length)}
          sub={`of ${data.column_count} total`}
          variant={
            data.columns.filter((c) => c.issues.length === 0).length === data.column_count
              ? "good"
              : "default"
          }
        />
      </motion.div>

      {/* ── Missing values + Outlier charts side by side ───────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Section title="Missing Values" icon={AlertTriangle}>
          {data.missing_summary.chart_spec ? (
            <div className="rounded-xl border border-border/60 bg-card/70 p-4">
              <PlotlyChart spec={data.missing_summary.chart_spec} />
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center rounded-xl border border-border/60 bg-card/70 py-10 gap-3">
              <CheckCircle2 className="h-7 w-7 text-emerald-400" />
              <p className="text-sm text-muted-foreground">No missing values detected</p>
            </div>
          )}
        </Section>

        <Section title="Outlier Distribution" icon={TrendingDown}>
          {data.outlier_summary.chart_spec ? (
            <div className="rounded-xl border border-border/60 bg-card/70 p-4">
              <PlotlyChart spec={data.outlier_summary.chart_spec} />
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center rounded-xl border border-border/60 bg-card/70 py-10 gap-3">
              <CheckCircle2 className="h-7 w-7 text-emerald-400" />
              <p className="text-sm text-muted-foreground">No outliers detected</p>
            </div>
          )}
        </Section>
      </div>

      {/* ── Column health table ─────────────────────────────────────────── */}
      <Section title="Column Health" icon={FileSearch}>
        <ColumnHealthTable columns={data.columns} />
      </Section>

      {/* ── Recommendations ─────────────────────────────────────────────── */}
      <Section title="Recommendations" icon={Sparkles}>
        <div className="space-y-3">
          {data.recommendations.map((rec, i) => (
            <RecommendationCard key={i} rec={rec} />
          ))}
        </div>
      </Section>
    </motion.div>
  );
}
