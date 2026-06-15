"use client";

import { useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { useMutation } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import type { Variants } from "framer-motion";
import {
  ArrowLeft,
  BarChart2,
  BookmarkCheck,
  ChevronDown,
  ChevronUp,
  Gauge,
  Loader2,
  Save,
  Sparkles,
  TrendingDown,
  TrendingUp,
  Zap,
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { generateDashboard, saveDashboard } from "@/lib/api/dashboards";
import { ApiError } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type {
  ChartPanel,
  GenerateDashboardResponse,
  KPIMetric,
  LayoutConfig,
} from "@/lib/api/types";

// Plotly loaded client-side only (heavy bundle)
const Plot = dynamic(() => import("react-plotly.js"), {
  ssr: false,
  loading: () => (
    <div className="h-48 flex items-center justify-center text-muted-foreground text-sm">
      <Loader2 className="h-4 w-4 animate-spin mr-2" /> Loading chart…
    </div>
  ),
});

// ---------------------------------------------------------------------------
// Animations
// ---------------------------------------------------------------------------

const fadeUp: Variants = {
  hidden: { opacity: 0, y: 10 },
  show: { opacity: 1, y: 0, transition: { duration: 0.22 } },
};

const stagger: Variants = {
  show: { transition: { staggerChildren: 0.05 } },
};

// ---------------------------------------------------------------------------
// KPI card
// ---------------------------------------------------------------------------

function KPICard({ kpi }: { kpi: KPIMetric }) {
  const trendIcon =
    kpi.trend === "up" ? (
      <TrendingUp className="h-3.5 w-3.5 text-emerald-500" />
    ) : kpi.trend === "down" ? (
      <TrendingDown className="h-3.5 w-3.5 text-red-500" />
    ) : null;

  const changeBadgeClass =
    kpi.trend === "up"
      ? "text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-900/30"
      : kpi.trend === "down"
      ? "text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/30"
      : "text-muted-foreground bg-muted";

  return (
    <motion.div
      variants={fadeUp}
      className="rounded-xl border border-border/60 bg-card/60 p-4 flex flex-col gap-1.5 min-w-0"
    >
      <p className="text-[11px] font-medium text-muted-foreground truncate uppercase tracking-wide">
        {kpi.label}
      </p>
      <p className="text-2xl font-bold tabular-nums text-foreground truncate">
        {kpi.formatted_value}
      </p>
      {kpi.change_pct !== null && (
        <div className="flex items-center gap-1.5">
          {trendIcon}
          <span
            className={cn(
              "text-[10px] font-semibold rounded-md px-1.5 py-0.5",
              changeBadgeClass
            )}
          >
            {kpi.change_pct > 0 ? "+" : ""}
            {kpi.change_pct.toFixed(1)}%
          </span>
          <span className="text-[10px] text-muted-foreground/60">vs prior half</span>
        </div>
      )}
      <p className="text-[10px] text-muted-foreground/50 capitalize">{kpi.aggregation}</p>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Chart card
// ---------------------------------------------------------------------------

function ChartCard({ chart }: { chart: ChartPanel }) {
  return (
    <motion.div
      variants={fadeUp}
      className="rounded-xl border border-border/60 bg-card/60 p-4 overflow-hidden"
    >
      <p className="text-xs font-semibold text-foreground mb-3 truncate">{chart.title}</p>
      <Plot
        data={(chart.chart_spec as { data: Plotly.Data[] }).data}
        layout={{
          ...((chart.chart_spec as { layout: Partial<Plotly.Layout> }).layout ?? {}),
          autosize: true,
          margin: { l: 40, r: 10, t: 10, b: 40 },
          paper_bgcolor: "transparent",
          plot_bgcolor: "transparent",
          font: { size: 11, color: "currentColor" },
        }}
        config={{ displayModeBar: false, responsive: true }}
        style={{ width: "100%", height: "200px" }}
        useResizeHandler
      />
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Dashboard results panel
// ---------------------------------------------------------------------------

function ScoreBadge({ score }: { score: number }) {
  const color =
    score >= 75
      ? "text-emerald-600 bg-emerald-50 dark:bg-emerald-900/30 dark:text-emerald-400"
      : score >= 50
      ? "text-amber-600 bg-amber-50 dark:bg-amber-900/30 dark:text-amber-400"
      : "text-red-600 bg-red-50 dark:bg-red-900/30 dark:text-red-400";

  return (
    <span className={cn("text-xs font-semibold rounded-md px-2 py-0.5", color)}>
      Score {score}/100
    </span>
  );
}

interface ResultsPanelProps {
  resp: GenerateDashboardResponse;
  onSave: () => void;
  isSaving: boolean;
  saved: boolean;
}

function ResultsPanel({ resp, onSave, isSaving, saved }: ResultsPanelProps) {
  const [showRecs, setShowRecs] = useState(true);

  // Build ordered chart map for layout
  const chartMap = Object.fromEntries(resp.charts.map((c) => [c.id, c]));

  return (
    <motion.div
      variants={stagger}
      initial="hidden"
      animate="show"
      className="space-y-6"
    >
      {/* Header row */}
      <motion.div variants={fadeUp} className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-base font-semibold text-foreground">{resp.dashboard_name}</h2>
          <div className="flex items-center gap-2 mt-1">
            <ScoreBadge score={resp.score} />
            {resp.cache_hit && (
              <Badge variant="secondary" className="text-[10px]">
                cached
              </Badge>
            )}
            <span className="text-[10px] text-muted-foreground/50 tabular-nums">
              {resp.generation_time_ms.toFixed(0)} ms
            </span>
          </div>
        </div>
        <Button
          onClick={onSave}
          disabled={isSaving || saved}
          size="sm"
          className="gap-2 shrink-0"
          variant={saved ? "secondary" : "default"}
        >
          {saved ? (
            <>
              <BookmarkCheck className="h-4 w-4" />
              Saved
            </>
          ) : isSaving ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Saving…
            </>
          ) : (
            <>
              <Save className="h-4 w-4" />
              Save Dashboard
            </>
          )}
        </Button>
      </motion.div>

      {/* KPI row */}
      {resp.kpis.length > 0 && (
        <motion.section variants={fadeUp}>
          <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground mb-3 flex items-center gap-1.5">
            <Gauge className="h-3.5 w-3.5" />
            Key Metrics
          </p>
          <motion.div
            variants={stagger}
            className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-3"
          >
            {resp.kpis.map((kpi) => (
              <KPICard key={kpi.id} kpi={kpi} />
            ))}
          </motion.div>
        </motion.section>
      )}

      {/* Charts — follow layout rows */}
      {resp.layout.rows.length > 0 && (
        <motion.section variants={fadeUp}>
          <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground mb-3 flex items-center gap-1.5">
            <BarChart2 className="h-3.5 w-3.5" />
            Charts
          </p>
          <motion.div variants={stagger} className="space-y-4">
            {resp.layout.rows.map((row, ri) => (
              <div
                key={ri}
                className={cn(
                  "grid gap-4",
                  row.length === 1 ? "grid-cols-1" : "grid-cols-1 md:grid-cols-2"
                )}
              >
                {row.map((cell) => {
                  const chart = chartMap[cell.id];
                  return chart ? <ChartCard key={cell.id} chart={chart} /> : null;
                })}
              </div>
            ))}
          </motion.div>
        </motion.section>
      )}

      {/* Recommendations */}
      {resp.recommendations.length > 0 && (
        <motion.div variants={fadeUp} className="rounded-xl border border-border/60 bg-card/60 p-4">
          <button
            onClick={() => setShowRecs((s) => !s)}
            className="flex items-center justify-between w-full"
          >
            <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground flex items-center gap-1.5">
              <Zap className="h-3.5 w-3.5 text-amber-500" />
              Recommendations
            </p>
            {showRecs ? (
              <ChevronUp className="h-3.5 w-3.5 text-muted-foreground" />
            ) : (
              <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
            )}
          </button>
          <AnimatePresence>
            {showRecs && (
              <motion.ul
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1, transition: { duration: 0.2 } }}
                exit={{ height: 0, opacity: 0, transition: { duration: 0.15 } }}
                className="mt-3 space-y-2 overflow-hidden"
              >
                {resp.recommendations.map((rec, i) => (
                  <li key={i} className="flex items-start gap-2.5">
                    <span className="mt-1 h-4 w-4 shrink-0 flex items-center justify-center rounded-sm bg-amber-500/10">
                      <Zap className="h-2.5 w-2.5 text-amber-500" />
                    </span>
                    <span className="text-sm text-foreground/85 leading-relaxed">{rec}</span>
                  </li>
                ))}
              </motion.ul>
            )}
          </AnimatePresence>
        </motion.div>
      )}
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Main workspace
// ---------------------------------------------------------------------------

interface DashboardGeneratorWorkspaceProps {
  datasetId: string;
}

export function DashboardGeneratorWorkspace({
  datasetId,
}: DashboardGeneratorWorkspaceProps) {
  const [prompt, setPrompt] = useState("");
  const [maxKpis, setMaxKpis] = useState(6);
  const [maxCharts, setMaxCharts] = useState(6);
  const [result, setResult] = useState<GenerateDashboardResponse | null>(null);
  const [saved, setSaved] = useState(false);

  const generateMutation = useMutation({
    mutationFn: () =>
      generateDashboard({
        dataset_id: datasetId,
        prompt: prompt.trim() || "Create an executive dashboard",
        max_kpis: maxKpis,
        max_charts: maxCharts,
      }),
    onSuccess: (data) => {
      setResult(data);
      setSaved(false);
    },
    onError: (err: unknown) => {
      const message =
        err instanceof ApiError
          ? err.message
          : "Dashboard generation failed. Please try again.";
      toast.error(message);
    },
  });

  const saveMutation = useMutation({
    mutationFn: () => {
      if (!result) throw new Error("No dashboard to save");
      return saveDashboard({
        dashboard_config: {
          dashboard_id: null,
          dashboard_name: result.dashboard_name,
          dataset_id: result.dataset_id,
          owner_sub: "",
          kpis: result.kpis,
          charts: result.charts,
          layout: result.layout,
          recommendations: result.recommendations,
          score: result.score,
          generation_time_ms: result.generation_time_ms,
          cache_hit: result.cache_hit,
          created_at: new Date().toISOString(),
        },
      });
    },
    onSuccess: (data) => {
      setSaved(true);
      toast.success(`Dashboard "${data.dashboard_name}" saved.`);
    },
    onError: (err: unknown) => {
      const message =
        err instanceof ApiError ? err.message : "Failed to save dashboard.";
      toast.error(message);
    },
  });

  const canGenerate =
    !generateMutation.isPending && !saveMutation.isPending;

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && canGenerate) {
      e.preventDefault();
      generateMutation.mutate();
    }
  };

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
          <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-primary/10">
            <BarChart2 className="h-3 w-3 text-primary" />
          </div>
          <span className="ml-1.5 text-sm font-medium text-foreground">
            Executive Dashboard
          </span>
        </div>

        {result && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground tabular-nums">
              {result.kpis.length} KPIs · {result.charts.length} charts
            </span>
            {result.cache_hit && (
              <Badge variant="secondary" className="text-[10px]">
                cached
              </Badge>
            )}
          </div>
        )}
      </header>

      {/* ── Body ────────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-5xl mx-auto px-4 py-6 space-y-6">
          {/* Controls */}
          <div className="rounded-xl border border-border/60 bg-card/60 p-4 space-y-4">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Dashboard Configuration
            </p>

            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={2}
              placeholder="Create an executive dashboard focused on revenue and sales trends…"
              className={cn(
                "w-full rounded-lg border border-border/60 bg-background px-3 py-2.5",
                "text-sm text-foreground placeholder:text-muted-foreground/60",
                "focus:outline-none focus:ring-1 focus:ring-ring resize-none transition-colors"
              )}
              aria-label="Dashboard prompt"
            />

            <div className="flex flex-wrap gap-4 items-end">
              <div className="flex flex-col gap-1 min-w-[120px]">
                <label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
                  Max KPIs
                </label>
                <input
                  type="number"
                  min={1}
                  max={10}
                  value={maxKpis}
                  onChange={(e) =>
                    setMaxKpis(Math.min(10, Math.max(1, Number(e.target.value))))
                  }
                  className={cn(
                    "rounded-lg border border-border/60 bg-background px-3 py-1.5",
                    "text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring w-20"
                  )}
                />
              </div>

              <div className="flex flex-col gap-1 min-w-[120px]">
                <label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
                  Max Charts
                </label>
                <input
                  type="number"
                  min={1}
                  max={10}
                  value={maxCharts}
                  onChange={(e) =>
                    setMaxCharts(Math.min(10, Math.max(1, Number(e.target.value))))
                  }
                  className={cn(
                    "rounded-lg border border-border/60 bg-background px-3 py-1.5",
                    "text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring w-20"
                  )}
                />
              </div>

              <Button
                onClick={() => generateMutation.mutate()}
                disabled={!canGenerate}
                className="gap-2 ml-auto"
              >
                {generateMutation.isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Generating…
                  </>
                ) : (
                  <>
                    <Sparkles className="h-4 w-4" />
                    Generate Dashboard
                  </>
                )}
              </Button>
            </div>

            <p className="text-[10px] text-muted-foreground/60">
              Press ⌘ + Enter to generate
            </p>
          </div>

          {/* Empty state */}
          {!result && !generateMutation.isPending && (
            <div className="flex flex-col items-center justify-center py-20 text-center gap-3 text-muted-foreground">
              <div className="flex h-14 w-14 items-center justify-center rounded-xl bg-primary/5 border border-primary/10">
                <BarChart2 className="h-7 w-7 text-primary/50" />
              </div>
              <div>
                <p className="text-sm font-medium text-foreground/70">
                  Generate an AI Executive Dashboard
                </p>
                <p className="text-xs mt-1 max-w-xs opacity-70">
                  Deterministic KPI selection, chart recommendation, and layout
                  generation — all server-side. No LLM touches chart specs.
                </p>
              </div>
            </div>
          )}

          {/* Loading */}
          {generateMutation.isPending && (
            <div className="flex flex-col items-center justify-center py-20 gap-3 text-muted-foreground">
              <Loader2 className="h-8 w-8 animate-spin" />
              <p className="text-sm">Analysing data and building dashboard…</p>
            </div>
          )}

          {/* Results */}
          <AnimatePresence mode="wait">
            {result && !generateMutation.isPending && (
              <ResultsPanel
                key="results"
                resp={result}
                onSave={() => saveMutation.mutate()}
                isSaving={saveMutation.isPending}
                saved={saved}
              />
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
