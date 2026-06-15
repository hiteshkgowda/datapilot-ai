"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import type { Variants } from "framer-motion";
import {
  Activity,
  AlertTriangle,
  BarChart2,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  Minus,
  RefreshCw,
  Sparkles,
  TrendingDown,
  TrendingUp,
  XCircle,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { PlotlyChart } from "@/components/ask/PlotlyChart";
import { getKPIMonitor } from "@/lib/api/kpi-monitor";
import type {
  KPIAlert,
  KPIAlertSeverity,
  KPIHealth,
  KPIMonitorResponse,
  KPIPriority,
  KPIRecommendation,
  KPIStat,
  KPITrend,
} from "@/lib/api/types";

// ─── Animations ───────────────────────────────────────────────────────────────

const fadeUp: Variants = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.2 } },
};

const stagger: Variants = {
  show: { transition: { staggerChildren: 0.06 } },
};

// ─── Config maps ──────────────────────────────────────────────────────────────

const HEALTH_CONFIG: Record<KPIHealth, {
  label: string; color: string; bg: string; border: string; dot: string; Icon: React.ElementType;
}> = {
  healthy:  { label: "Healthy",  color: "text-emerald-400", bg: "bg-emerald-500/10", border: "border-emerald-500/20", dot: "bg-emerald-400", Icon: CheckCircle2 },
  warning:  { label: "Warning",  color: "text-amber-400",   bg: "bg-amber-500/10",   border: "border-amber-500/20",   dot: "bg-amber-400",   Icon: AlertTriangle },
  critical: { label: "Critical", color: "text-red-400",     bg: "bg-red-500/10",     border: "border-red-500/20",     dot: "bg-red-500",     Icon: XCircle },
  unknown:  { label: "Unknown",  color: "text-muted-foreground", bg: "bg-muted/30", border: "border-border/40", dot: "bg-muted-foreground", Icon: Minus },
};

const SEVERITY_CONFIG: Record<KPIAlertSeverity, {
  label: string; color: string; bg: string; border: string;
}> = {
  critical: { label: "Critical", color: "text-red-400",    bg: "bg-red-500/8",    border: "border-red-500/20" },
  high:     { label: "High",     color: "text-orange-400", bg: "bg-orange-500/8", border: "border-orange-500/20" },
  medium:   { label: "Medium",   color: "text-amber-400",  bg: "bg-amber-500/8",  border: "border-amber-500/20" },
  low:      { label: "Low",      color: "text-sky-400",    bg: "bg-sky-500/8",    border: "border-sky-500/20" },
};

const PRIORITY_CONFIG: Record<KPIPriority, { label: string; color: string; dot: string }> = {
  critical: { label: "Critical", color: "text-red-400",    dot: "bg-red-500" },
  high:     { label: "High",     color: "text-orange-400", dot: "bg-orange-500" },
  medium:   { label: "Medium",   color: "text-amber-400",  dot: "bg-amber-500" },
  low:      { label: "Low",      color: "text-sky-400",    dot: "bg-sky-500" },
};

const TREND_ICON: Record<KPITrend, React.ElementType> = {
  up: TrendingUp,
  down: TrendingDown,
  flat: Minus,
};

const TREND_COLOR: Record<KPITrend, string> = {
  up: "text-emerald-400",
  down: "text-red-400",
  flat: "text-muted-foreground",
};

// ─── Sparkline ────────────────────────────────────────────────────────────────

function Sparkline({ data, health }: { data: number[]; health: KPIHealth }) {
  if (data.length < 2) return null;

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const W = 80;
  const H = 28;
  const pad = 2;

  const pts = data.map((v, i) => {
    const x = pad + (i / (data.length - 1)) * (W - pad * 2);
    const y = H - pad - ((v - min) / range) * (H - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  const strokeColor =
    health === "critical" ? "#ef4444" :
    health === "warning"  ? "#f59e0b" :
                            "#6366f1";

  return (
    <svg width={W} height={H} className="overflow-visible">
      <polyline
        points={pts.join(" ")}
        fill="none"
        stroke={strokeColor}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity="0.9"
      />
    </svg>
  );
}

// ─── Overall health banner ────────────────────────────────────────────────────

function OverallHealthBanner({ data }: { data: KPIMonitorResponse }) {
  const cfg = HEALTH_CONFIG[data.overall_health];
  const Icon = cfg.Icon;

  return (
    <div className={cn(
      "flex flex-col sm:flex-row sm:items-center justify-between gap-4 rounded-2xl border p-5",
      cfg.bg, cfg.border
    )}>
      <div className="flex items-center gap-3">
        <div className={cn("flex h-10 w-10 shrink-0 items-center justify-center rounded-xl", cfg.bg, "border", cfg.border)}>
          <Icon className={cn("h-5 w-5", cfg.color)} />
        </div>
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className={cn("text-base font-semibold", cfg.color)}>
              System {cfg.label}
            </span>
            {data.cache_hit && (
              <span className="text-[10px] uppercase tracking-wide text-muted-foreground/60">cached</span>
            )}
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">
            {data.row_count.toLocaleString()} rows · {data.kpis.length} KPI{data.kpis.length !== 1 ? "s" : ""} monitored
            {data.time_column && ` · time axis: ${data.time_column}`}
            {" · "}{data.analysis_time_ms.toFixed(0)} ms
          </p>
        </div>
      </div>

      <div className="flex items-center gap-3 shrink-0">
        <div className="flex items-center gap-2 text-xs">
          <span className="flex items-center gap-1.5 text-emerald-400">
            <span className="h-2 w-2 rounded-full bg-emerald-400" />
            {data.healthy_count} healthy
          </span>
          <span className="flex items-center gap-1.5 text-amber-400">
            <span className="h-2 w-2 rounded-full bg-amber-400" />
            {data.warning_count} warning
          </span>
          <span className="flex items-center gap-1.5 text-red-400">
            <span className="h-2 w-2 rounded-full bg-red-400" />
            {data.critical_count} critical
          </span>
        </div>
      </div>
    </div>
  );
}

// ─── KPI card ─────────────────────────────────────────────────────────────────

function KPICard({ kpi, onClick, selected }: {
  kpi: KPIStat;
  onClick: () => void;
  selected: boolean;
}) {
  const hCfg = HEALTH_CONFIG[kpi.health];
  const TrendIcon = TREND_ICON[kpi.trend];

  return (
    <button
      onClick={onClick}
      className={cn(
        "group w-full text-left rounded-xl border p-4 transition-all duration-150",
        "hover:border-primary/40 hover:bg-primary/5 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40",
        selected
          ? "border-primary/50 bg-primary/8 shadow-[0_0_0_1px_hsl(var(--primary)/0.2)]"
          : "border-border/60 bg-card/70"
      )}
    >
      {/* Header row */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground truncate">
            {kpi.label}
          </p>
        </div>
        <div className={cn(
          "flex items-center gap-1 shrink-0 rounded-full px-1.5 py-0.5",
          hCfg.bg, hCfg.border, "border"
        )}>
          <span className={cn("h-1.5 w-1.5 rounded-full", hCfg.dot)} />
          <span className={cn("text-[10px] font-medium", hCfg.color)}>{hCfg.label}</span>
        </div>
      </div>

      {/* Value + trend */}
      <div className="flex items-end justify-between mt-2">
        <div>
          <span className="text-2xl font-bold tabular-nums text-foreground leading-none">
            {kpi.formatted_value}
          </span>
          {kpi.change_pct !== null && (
            <div className={cn("flex items-center gap-0.5 mt-1 text-xs font-medium", TREND_COLOR[kpi.trend])}>
              <TrendIcon className="h-3.5 w-3.5" />
              {Math.abs(kpi.change_pct).toFixed(1)}%
            </div>
          )}
        </div>
        <Sparkline data={kpi.sparkline} health={kpi.health} />
      </div>

      {/* Stats row */}
      <div className="mt-3 pt-3 border-t border-border/40 grid grid-cols-3 gap-1 text-center">
        {[
          ["Min", kpi.min_value],
          ["Mean", kpi.mean],
          ["Max", kpi.max_value],
        ].map(([label, val]) => (
          <div key={String(label)}>
            <p className="text-[10px] text-muted-foreground/60">{label}</p>
            <p className="text-[11px] font-mono font-medium text-foreground">
              {typeof val === "number"
                ? Math.abs(val) >= 1000
                  ? (val / 1000).toFixed(1) + "K"
                  : val.toFixed(Math.abs(val) < 1 ? 3 : 1)
                : val}
            </p>
          </div>
        ))}
      </div>

      {kpi.alert_count > 0 && (
        <div className="mt-2 flex items-center gap-1 text-[10px] text-amber-400">
          <AlertTriangle className="h-3 w-3" />
          {kpi.alert_count} alert{kpi.alert_count !== 1 ? "s" : ""}
        </div>
      )}
    </button>
  );
}

// ─── Alert timeline ───────────────────────────────────────────────────────────

function AlertTimeline({ alerts }: { alerts: KPIAlert[] }) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? alerts : alerts.slice(0, 8);

  if (alerts.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-xl border border-border/60 bg-card/60 py-10 gap-3">
        <CheckCircle2 className="h-7 w-7 text-emerald-400" />
        <p className="text-sm text-muted-foreground">No threshold breaches detected</p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-border/60 bg-card/70 overflow-hidden">
      <div className="px-4 py-3 border-b border-border/40 flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
          {alerts.length} alert{alerts.length !== 1 ? "s" : ""}
        </span>
        <div className="flex gap-2">
          {(["critical", "high", "medium"] as KPIAlertSeverity[]).map((sev) => {
            const n = alerts.filter((a) => a.severity === sev).length;
            if (!n) return null;
            return (
              <span key={sev} className={cn("text-[10px] font-medium", SEVERITY_CONFIG[sev].color)}>
                {n} {sev}
              </span>
            );
          })}
        </div>
      </div>

      <div className="divide-y divide-border/30">
        {visible.map((alert, i) => {
          const cfg = SEVERITY_CONFIG[alert.severity];
          return (
            <div key={i} className={cn("flex items-start gap-3 px-4 py-3", cfg.bg)}>
              {/* Timeline dot */}
              <div className="relative flex flex-col items-center shrink-0 mt-0.5">
                <span className={cn("h-2.5 w-2.5 rounded-full border-2 border-background", cfg.color.replace("text-", "bg-"))} />
                {i < visible.length - 1 && (
                  <span className="w-px flex-1 bg-border/40 mt-1 min-h-[12px]" />
                )}
              </div>

              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className={cn("text-[10px] font-semibold uppercase tracking-wide", cfg.color)}>
                    {alert.severity}
                  </span>
                  <span className="text-xs font-medium text-foreground truncate">
                    {alert.kpi_name}
                  </span>
                  {alert.label && (
                    <span className="flex items-center gap-1 text-[10px] text-muted-foreground/60">
                      <Clock className="h-3 w-3" />
                      {alert.label}
                    </span>
                  )}
                </div>
                <p className="text-xs text-muted-foreground mt-0.5 truncate">
                  {alert.message}
                </p>
              </div>

              <div className="shrink-0 text-right">
                <span className="text-xs font-mono font-medium text-foreground">
                  row {alert.row_index}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {alerts.length > 8 && (
        <button
          onClick={() => setExpanded((v) => !v)}
          className="w-full flex items-center justify-center gap-1.5 py-2.5 text-xs text-muted-foreground hover:text-foreground border-t border-border/40 transition-colors"
        >
          {expanded ? (
            <><ChevronUp className="h-3.5 w-3.5" /> Show less</>
          ) : (
            <><ChevronDown className="h-3.5 w-3.5" /> Show {alerts.length - 8} more</>
          )}
        </button>
      )}
    </div>
  );
}

// ─── Recommendations ──────────────────────────────────────────────────────────

function RecommendationList({ recs }: { recs: KPIRecommendation[] }) {
  return (
    <div className="space-y-3">
      {recs.map((rec, i) => {
        const cfg = PRIORITY_CONFIG[rec.priority];
        return (
          <div
            key={i}
            className="flex items-start gap-3 rounded-xl border border-border/60 bg-card/70 p-4"
          >
            <span className={cn("mt-1.5 h-2 w-2 rounded-full shrink-0", cfg.dot)} />
            <div className="min-w-0 space-y-1">
              <div className="flex items-center gap-2 flex-wrap">
                <span className={cn("text-[10px] font-semibold uppercase tracking-wide", cfg.color)}>
                  {cfg.label}
                </span>
                {rec.kpi !== "all" && (
                  <span className="text-[10px] font-mono text-muted-foreground/70">{rec.kpi}</span>
                )}
              </div>
              <p className="text-sm font-medium text-foreground">{rec.issue}</p>
              <p className="text-sm text-muted-foreground">{rec.action}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─── Loading skeleton ─────────────────────────────────────────────────────────

function LoadingSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-20 rounded-2xl" />
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
        {[...Array(8)].map((_, i) => (
          <Skeleton key={i} className="h-40 rounded-xl" />
        ))}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Skeleton className="h-72 rounded-xl" />
        <Skeleton className="h-72 rounded-xl" />
      </div>
    </div>
  );
}

// ─── Section label ────────────────────────────────────────────────────────────

function SectionHeader({ icon: Icon, title, count }: {
  icon: React.ElementType;
  title: string;
  count?: number;
}) {
  return (
    <div className="flex items-center gap-2">
      <Icon className="h-4 w-4 text-primary/70 shrink-0" />
      <h2 className="text-sm font-semibold text-foreground">{title}</h2>
      {count !== undefined && (
        <span className="ml-1 rounded-full bg-muted/60 px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
          {count}
        </span>
      )}
    </div>
  );
}

// ─── Main dashboard ───────────────────────────────────────────────────────────

interface KPIMonitorDashboardProps {
  datasetId: string;
}

export function KPIMonitorDashboard({ datasetId }: KPIMonitorDashboardProps) {
  const [selectedKpi, setSelectedKpi] = useState<KPIStat | null>(null);

  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["kpi-monitor", datasetId],
    queryFn: () => getKPIMonitor(datasetId),
    staleTime: 5 * 60_000,
    retry: 1,
  });

  if (isLoading) {
    return (
      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-8">
        <LoadingSkeleton />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-4">
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

  const displayed = selectedKpi ?? (data.kpis[0] ?? null);

  return (
    <motion.div
      variants={stagger}
      initial="hidden"
      animate="show"
      className="max-w-6xl mx-auto px-4 sm:px-6 py-8 space-y-8"
    >
      {/* ── Page header ──────────────────────────────────────────────── */}
      <motion.div variants={fadeUp} className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 shrink-0">
            <Activity className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-foreground">KPI Monitor</h1>
            <p className="text-sm text-muted-foreground">
              Real-time health and trend analysis
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

      {/* ── Overall health banner ─────────────────────────────────────── */}
      <motion.div variants={fadeUp}>
        <OverallHealthBanner data={data} />
      </motion.div>

      {/* ── KPI cards grid ───────────────────────────────────────────── */}
      <motion.div variants={fadeUp} className="space-y-4">
        <SectionHeader icon={Zap} title="KPI Cards" count={data.kpis.length} />
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
          {data.kpis.map((kpi) => (
            <KPICard
              key={kpi.column}
              kpi={kpi}
              selected={displayed?.column === kpi.column}
              onClick={() =>
                setSelectedKpi(
                  displayed?.column === kpi.column ? null : kpi
                )
              }
            />
          ))}
        </div>
      </motion.div>

      {/* ── Trend chart ──────────────────────────────────────────────── */}
      <AnimatePresence mode="wait">
        {displayed?.chart_spec && (
          <motion.div
            key={displayed.column}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.18 }}
          >
            <div className="space-y-4">
              <SectionHeader icon={BarChart2} title={`Trend — ${displayed.label}`} />
              <div className="rounded-xl border border-border/60 bg-card/70 p-4">
                {/* Health indicator strip */}
                <div className="flex items-center gap-4 mb-4 flex-wrap">
                  {[
                    { label: "Current", value: displayed.formatted_value },
                    { label: "Mean",    value: displayed.mean >= 1000
                        ? (displayed.mean / 1000).toFixed(1) + "K"
                        : displayed.mean.toFixed(2) },
                    { label: "Std Dev", value: displayed.std >= 1000
                        ? (displayed.std / 1000).toFixed(1) + "K"
                        : displayed.std.toFixed(2) },
                    { label: "Change",  value: displayed.change_pct !== null
                        ? `${displayed.change_pct > 0 ? "+" : ""}${displayed.change_pct.toFixed(1)}%`
                        : "N/A" },
                  ].map(({ label, value }) => (
                    <div key={label} className="flex flex-col">
                      <span className="text-[10px] text-muted-foreground/60 uppercase tracking-wide">{label}</span>
                      <span className="text-sm font-semibold tabular-nums text-foreground">{value}</span>
                    </div>
                  ))}
                  <div className="ml-auto flex items-center gap-1.5">
                    {(() => {
                      const hCfg = HEALTH_CONFIG[displayed.health];
                      const HIcon = hCfg.Icon;
                      return (
                        <span className={cn("flex items-center gap-1 text-xs font-medium", hCfg.color)}>
                          <HIcon className="h-3.5 w-3.5" />
                          {hCfg.label}
                        </span>
                      );
                    })()}
                  </div>
                </div>
                <PlotlyChart spec={displayed.chart_spec} />
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Alert timeline + recommendations (2-col on lg) ───────────── */}
      <motion.div
        variants={fadeUp}
        className="grid grid-cols-1 lg:grid-cols-2 gap-6"
      >
        {/* Alert timeline */}
        <div className="space-y-4">
          <SectionHeader icon={AlertTriangle} title="Alert Timeline" count={data.alerts.length} />
          <AlertTimeline alerts={data.alerts} />
        </div>

        {/* Recommendations */}
        <div className="space-y-4">
          <SectionHeader icon={Sparkles} title="Recommendations" count={data.recommendations.length} />
          <RecommendationList recs={data.recommendations} />
        </div>
      </motion.div>
    </motion.div>
  );
}
