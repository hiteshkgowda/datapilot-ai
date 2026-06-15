"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import GridLayout, { type Layout, type LayoutItem } from "react-grid-layout";
import { motion } from "framer-motion";
import type { Variants } from "framer-motion";
import {
  BarChart2,
  DollarSign,
  Gauge,
  GripHorizontal,
  LayoutDashboard,
  Loader2,
  Minus,
  Pencil,
  Save,
  Sparkles,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { PlotlyChart } from "@/components/ask/PlotlyChart";
import {
  generateDashboard,
  saveDashboard,
  getDashboard,
} from "@/lib/api/dashboards";
import type {
  KPIMetric,
  ChartPanel,
  LayoutConfig,
  DashboardConfig,
} from "@/lib/api/types";

// ─── Types ────────────────────────────────────────────────────────────────────

type BuilderPhase = "configure" | "generating" | "editor";

interface Template {
  id: string;
  label: string;
  description: string;
  icon: React.ElementType;
  prompt: string;
}

// ─── Constants ────────────────────────────────────────────────────────────────

const TEMPLATES: Template[] = [
  {
    id: "executive",
    label: "Executive Overview",
    description: "Top KPIs and trend analysis",
    icon: LayoutDashboard,
    prompt:
      "Create an executive overview dashboard with the most important KPIs (revenue, count, growth) and trend charts showing performance over time.",
  },
  {
    id: "sales",
    label: "Sales & Revenue",
    description: "Revenue metrics and conversion",
    icon: TrendingUp,
    prompt:
      "Sales and revenue performance dashboard with period-over-period comparisons, top performers, and revenue breakdown charts.",
  },
  {
    id: "operations",
    label: "Operations",
    description: "Efficiency and productivity",
    icon: Gauge,
    prompt:
      "Operational efficiency dashboard with process metrics, throughput KPIs, and productivity trend analysis.",
  },
  {
    id: "marketing",
    label: "Marketing Analytics",
    description: "Campaigns and conversions",
    icon: Sparkles,
    prompt:
      "Marketing performance dashboard with conversion metrics, channel contribution analysis, and campaign efficiency KPIs.",
  },
  {
    id: "financial",
    label: "Financial Health",
    description: "Revenue, costs, and margins",
    icon: DollarSign,
    prompt:
      "Financial health dashboard with revenue, cost breakdown, profitability margins, and financial trend charts.",
  },
];

const COLS = 12;
const ROW_HEIGHT = 60;
const GRID_MARGIN: [number, number] = [12, 12];

const fadeUp: Variants = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.22 } },
};

const stagger: Variants = {
  show: { transition: { staggerChildren: 0.06 } },
};

// ─── Layout helpers ───────────────────────────────────────────────────────────

function buildInitialLayout(
  kpis: KPIMetric[],
  charts: ChartPanel[],
  layoutConfig: LayoutConfig
): LayoutItem[] {
  const items: LayoutItem[] = [];

  kpis.forEach((kpi, i) => {
    items.push({
      i: `kpi-${kpi.id}`,
      x: (i % 4) * 3,
      y: Math.floor(i / 4) * 2,
      w: 3,
      h: 2,
      minW: 2,
      minH: 2,
    });
  });

  const kpiRowCount = kpis.length > 0 ? Math.ceil(kpis.length / 4) * 2 : 0;
  let rowY = kpiRowCount;

  for (const row of layoutConfig.rows) {
    let x = 0;
    for (const cell of row) {
      if (!charts.find((c) => c.id === cell.id)) continue;
      const w = cell.width === "full" ? 12 : 6;
      items.push({
        i: `chart-${cell.id}`,
        x,
        y: rowY,
        w,
        h: 6,
        minW: 4,
        minH: 4,
      });
      x += w;
    }
    rowY += 6;
  }

  return items;
}

function buildLayoutConfig(
  rglLayout: LayoutItem[],
  _kpis: KPIMetric[],
  _charts: ChartPanel[]
): LayoutConfig {
  const kpiRow = rglLayout
    .filter((l) => l.i.startsWith("kpi-"))
    .sort((a, b) => a.y - b.y || a.x - b.x)
    .map((l) => l.i.slice(4));

  const chartItems = rglLayout
    .filter((l) => l.i.startsWith("chart-"))
    .sort((a, b) => a.y - b.y || a.x - b.x);

  const rowMap = new Map<number, LayoutItem[]>();
  for (const item of chartItems) {
    let placed = false;
    for (const [rowY, group] of rowMap.entries()) {
      if (Math.abs(item.y - rowY) <= 2) {
        group.push(item);
        placed = true;
        break;
      }
    }
    if (!placed) rowMap.set(item.y, [item]);
  }

  const rows = Array.from(rowMap.entries())
    .sort(([yA], [yB]) => yA - yB)
    .map(([, group]) =>
      group
        .sort((a, b) => a.x - b.x)
        .map((l) => ({
          id: l.i.slice(6),
          width: (l.w >= 10 ? "full" : "half") as "full" | "half",
        }))
    );

  return { kpi_row: kpiRow, rows };
}

// ─── KPI widget ───────────────────────────────────────────────────────────────

function KpiWidget({
  kpi,
  editMode,
}: {
  kpi: KPIMetric;
  editMode: boolean;
}) {
  const TrendIcon =
    kpi.trend === "up"
      ? TrendingUp
      : kpi.trend === "down"
      ? TrendingDown
      : Minus;
  const trendColor =
    kpi.trend === "up"
      ? "text-emerald-400"
      : kpi.trend === "down"
      ? "text-red-400"
      : "text-muted-foreground";

  return (
    <div className="relative h-full flex flex-col justify-between rounded-xl border border-border/60 bg-card/80 backdrop-blur-sm p-4 overflow-hidden select-none">
      <div className="absolute inset-0 bg-gradient-to-br from-primary/4 to-transparent pointer-events-none" />

      {editMode && (
        <div className="drag-handle absolute top-2 right-2 text-muted-foreground/40 hover:text-muted-foreground cursor-grab active:cursor-grabbing z-10">
          <GripHorizontal className="h-4 w-4" />
        </div>
      )}

      <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground truncate pr-6">
        {kpi.label}
      </p>

      <div className="flex items-end justify-between gap-2">
        <span className="text-2xl font-bold text-foreground tabular-nums leading-none">
          {kpi.formatted_value}
        </span>
        {kpi.change_pct !== null && (
          <div
            className={cn(
              "flex items-center gap-0.5 text-xs font-semibold shrink-0",
              trendColor
            )}
          >
            <TrendIcon className="h-3 w-3" />
            {Math.abs(kpi.change_pct).toFixed(1)}%
          </div>
        )}
      </div>

      <p className="text-[10px] text-muted-foreground/50 truncate">
        {kpi.aggregation} · {kpi.column}
      </p>
    </div>
  );
}

// ─── Chart widget ─────────────────────────────────────────────────────────────

function ChartWidget({
  chart,
  editMode,
}: {
  chart: ChartPanel;
  editMode: boolean;
}) {
  const Icon = chart.chart_type === "bar" ? BarChart2 : TrendingUp;

  return (
    <div className="h-full flex flex-col rounded-xl border border-border/60 bg-card/80 backdrop-blur-sm overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border/40 shrink-0">
        {editMode && (
          <div className="drag-handle text-muted-foreground/40 hover:text-muted-foreground cursor-grab active:cursor-grabbing">
            <GripHorizontal className="h-4 w-4 shrink-0" />
          </div>
        )}
        <Icon className="h-3.5 w-3.5 text-primary/60 shrink-0" />
        <span className="text-sm font-medium text-foreground truncate">
          {chart.title}
        </span>
      </div>
      <div className="flex-1 min-h-0 overflow-hidden">
        <PlotlyChart spec={chart.chart_spec} />
      </div>
    </div>
  );
}

// ─── Template card ────────────────────────────────────────────────────────────

function TemplateCard({
  template,
  selected,
  onSelect,
}: {
  template: Template;
  selected: boolean;
  onSelect: () => void;
}) {
  const Icon = template.icon;
  return (
    <button
      onClick={onSelect}
      className={cn(
        "relative flex flex-col gap-2.5 rounded-xl border p-4 text-left transition-all duration-150 w-full",
        "hover:border-primary/50 hover:bg-primary/5 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40",
        selected
          ? "border-primary bg-primary/8 shadow-[0_0_0_1px_hsl(var(--primary)/0.2)]"
          : "border-border/60 bg-card/60"
      )}
    >
      <div
        className={cn(
          "flex h-8 w-8 items-center justify-center rounded-lg transition-colors",
          selected
            ? "bg-primary/20 text-primary"
            : "bg-muted/60 text-muted-foreground"
        )}
      >
        <Icon className="h-4 w-4" />
      </div>
      <div>
        <p className="text-sm font-medium text-foreground leading-tight">
          {template.label}
        </p>
        <p className="text-xs text-muted-foreground mt-0.5 leading-snug">
          {template.description}
        </p>
      </div>
      {selected && (
        <div className="absolute top-2.5 right-2.5 h-2 w-2 rounded-full bg-primary" />
      )}
    </button>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export interface DashboardBuilderProps {
  datasetId?: string;
  dashboardId?: string;
}

export function DashboardBuilder({
  datasetId,
  dashboardId,
}: DashboardBuilderProps) {
  const [phase, setPhase] = useState<BuilderPhase>(
    dashboardId ? "generating" : "configure"
  );
  const [editMode, setEditMode] = useState(false);
  const [isDirty, setIsDirty] = useState(false);
  const [savedId, setSavedId] = useState<string | null>(dashboardId ?? null);
  const [dashboardName, setDashboardName] = useState("My Dashboard");
  const [kpis, setKpis] = useState<KPIMetric[]>([]);
  const [charts, setCharts] = useState<ChartPanel[]>([]);
  const [rglLayout, setRglLayout] = useState<LayoutItem[]>([]);
  const [activeDatasetId, setActiveDatasetId] = useState<string | null>(
    datasetId ?? null
  );
  const [selectedTemplate, setSelectedTemplate] = useState("executive");
  const [prompt, setPrompt] = useState(TEMPLATES[0].prompt);
  const [mounted, setMounted] = useState(false);
  const [gridWidth, setGridWidth] = useState(900);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMounted(true);
    if (!containerRef.current) return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width;
      if (w) setGridWidth(w);
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  // load saved dashboard
  const { data: loadedConfig, isError: loadError } = useQuery({
    queryKey: ["dashboard", dashboardId],
    queryFn: () => getDashboard(dashboardId!),
    enabled: !!dashboardId,
    staleTime: 60_000,
  });

  useEffect(() => {
    if (!loadedConfig) return;
    setDashboardName(loadedConfig.dashboard_name);
    setKpis(loadedConfig.kpis);
    setCharts(loadedConfig.charts);
    setActiveDatasetId(loadedConfig.dataset_id);
    setRglLayout(
      buildInitialLayout(loadedConfig.kpis, loadedConfig.charts, loadedConfig.layout)
    );
    setPhase("editor");
  }, [loadedConfig]);

  useEffect(() => {
    if (loadError) {
      toast.error("Failed to load dashboard");
      setPhase("configure");
    }
  }, [loadError]);

  // generate
  const generateMutation = useMutation({
    mutationFn: () =>
      generateDashboard({
        dataset_id: datasetId!,
        prompt,
        max_kpis: 8,
        max_charts: 4,
      }),
    onSuccess: (data) => {
      setDashboardName(data.dashboard_name);
      setKpis(data.kpis);
      setCharts(data.charts);
      setActiveDatasetId(data.dataset_id);
      setRglLayout(buildInitialLayout(data.kpis, data.charts, data.layout));
      setPhase("editor");
      setIsDirty(true);
    },
    onError: (err: Error) => {
      toast.error(`Generation failed: ${err.message}`);
      setPhase("configure");
    },
  });

  // save
  const saveMutation = useMutation({
    mutationFn: () => {
      const layout = buildLayoutConfig(rglLayout, kpis, charts);
      const config: DashboardConfig = {
        dashboard_id: savedId,
        dashboard_name: dashboardName,
        dataset_id: activeDatasetId!,
        owner_sub: "",
        kpis,
        charts,
        layout,
        recommendations: [],
        score: 0,
        generation_time_ms: 0,
        cache_hit: false,
        created_at: new Date().toISOString(),
      };
      return saveDashboard({ dashboard_config: config });
    },
    onSuccess: (data) => {
      setSavedId(data.dashboard_id);
      setIsDirty(false);
      toast.success("Dashboard saved");
    },
    onError: (err: Error) => {
      toast.error(`Save failed: ${err.message}`);
    },
  });

  const handleTemplateSelect = (t: Template) => {
    setSelectedTemplate(t.id);
    setPrompt(t.prompt);
  };

  const handleGenerate = () => {
    if (!datasetId) return;
    setPhase("generating");
    generateMutation.mutate();
  };

  // ── Configure ──────────────────────────────────────────────────────────────
  if (phase === "configure") {
    return (
      <div className="flex flex-col h-full overflow-y-auto">
        <div className="max-w-2xl mx-auto w-full px-6 py-10 space-y-8">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 shrink-0">
              <LayoutDashboard className="h-5 w-5 text-primary" />
            </div>
            <div>
              <h1 className="text-xl font-semibold text-foreground">
                Dashboard Builder
              </h1>
              <p className="text-sm text-muted-foreground">
                Generate an interactive dashboard from your data
              </p>
            </div>
          </div>

          <div className="space-y-3">
            <p className="text-sm font-medium text-foreground">Template</p>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
              {TEMPLATES.map((t) => (
                <TemplateCard
                  key={t.id}
                  template={t}
                  selected={selectedTemplate === t.id}
                  onSelect={() => handleTemplateSelect(t)}
                />
              ))}
            </div>
          </div>

          <div className="space-y-2">
            <label
              htmlFor="dash-prompt"
              className="text-sm font-medium text-foreground"
            >
              Prompt
            </label>
            <textarea
              id="dash-prompt"
              rows={3}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              className={cn(
                "w-full resize-none rounded-lg border border-border/60 bg-card/60 px-3 py-2.5",
                "text-sm text-foreground placeholder:text-muted-foreground/50",
                "focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/60",
                "transition-colors"
              )}
            />
          </div>

          <Button
            size="lg"
            className="w-full"
            onClick={handleGenerate}
            disabled={!prompt.trim() || !datasetId}
          >
            <Sparkles className="mr-2 h-4 w-4" />
            Generate Dashboard
          </Button>
        </div>
      </div>
    );
  }

  // ── Generating / loading ───────────────────────────────────────────────────
  if (phase === "generating") {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-6">
        <div className="relative">
          <div className="h-16 w-16 rounded-2xl bg-primary/10 flex items-center justify-center">
            <LayoutDashboard className="h-8 w-8 text-primary animate-pulse" />
          </div>
          <div className="absolute -top-1 -right-1">
            <Loader2 className="h-5 w-5 text-primary animate-spin" />
          </div>
        </div>
        <div className="text-center space-y-1">
          <p className="text-base font-medium text-foreground">
            {dashboardId ? "Loading dashboard…" : "Generating dashboard…"}
          </p>
          <p className="text-sm text-muted-foreground">
            Analysing your data and building visualisations
          </p>
        </div>
        <div className="flex gap-1.5">
          {[0, 0.2, 0.4].map((delay) => (
            <div
              key={delay}
              className="h-1.5 w-1.5 rounded-full bg-primary/60 animate-bounce"
              style={{ animationDelay: `${delay}s` }}
            />
          ))}
        </div>
      </div>
    );
  }

  // ── Editor ────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* toolbar */}
      <div className="shrink-0 flex items-center justify-between gap-4 px-5 py-3 border-b border-border/60 bg-background/80 backdrop-blur-sm">
        <div className="flex items-center gap-2.5 min-w-0">
          <LayoutDashboard className="h-4 w-4 text-primary shrink-0" />
          {editMode ? (
            <input
              value={dashboardName}
              onChange={(e) => {
                setDashboardName(e.target.value);
                setIsDirty(true);
              }}
              className="bg-transparent border-b border-primary/40 text-sm font-medium text-foreground focus:outline-none focus:border-primary px-0 min-w-0 w-48"
            />
          ) : (
            <h1 className="text-sm font-medium text-foreground truncate">
              {dashboardName}
            </h1>
          )}
          {isDirty && (
            <span className="text-[10px] text-muted-foreground/50 shrink-0 hidden sm:inline">
              unsaved
            </span>
          )}
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {datasetId && phase === "editor" && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setPhase("configure")}
              className="text-muted-foreground hidden sm:flex"
            >
              Regenerate
            </Button>
          )}
          <Button
            variant={editMode ? "default" : "outline"}
            size="sm"
            onClick={() => setEditMode((v) => !v)}
          >
            <Pencil className="mr-1.5 h-3.5 w-3.5" />
            {editMode ? "Done" : "Edit"}
          </Button>
          <Button
            size="sm"
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending || !isDirty}
          >
            {saveMutation.isPending ? (
              <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
            ) : (
              <Save className="mr-1.5 h-3.5 w-3.5" />
            )}
            Save
          </Button>
        </div>
      </div>

      {/* canvas */}
      <div className="flex-1 overflow-y-auto" style={{ overflowX: "hidden" }}>
        <div ref={containerRef} className="px-5 py-5 w-full">
          {editMode && (
            <p className="text-xs text-muted-foreground/50 mb-3 select-none">
              Drag widgets to rearrange · Drag corners to resize
            </p>
          )}

          {mounted && gridWidth > 0 ? (
            <motion.div
              variants={stagger}
              initial="hidden"
              animate="show"
            >
              <GridLayout
                layout={rglLayout}
                width={gridWidth}
                gridConfig={{
                  cols: COLS,
                  rowHeight: ROW_HEIGHT,
                  margin: GRID_MARGIN,
                  containerPadding: [0, 0],
                  maxRows: Infinity,
                }}
                dragConfig={{
                  enabled: editMode,
                  handle: ".drag-handle",
                  bounded: false,
                  threshold: 3,
                }}
                resizeConfig={{
                  enabled: editMode,
                  handles: ["se", "s", "e"],
                }}
                onLayoutChange={(layout: Layout) => {
                  setRglLayout([...layout]);
                  setIsDirty(true);
                }}
              >
                {kpis.map((kpi) => (
                  <motion.div key={`kpi-${kpi.id}`} variants={fadeUp}>
                    <KpiWidget kpi={kpi} editMode={editMode} />
                  </motion.div>
                ))}
                {charts.map((chart) => (
                  <motion.div key={`chart-${chart.id}`} variants={fadeUp}>
                    <ChartWidget chart={chart} editMode={editMode} />
                  </motion.div>
                ))}
              </GridLayout>
            </motion.div>
          ) : (
            <div className="grid grid-cols-4 gap-3">
              {[...Array(4)].map((_, i) => (
                <div
                  key={i}
                  className="h-[132px] rounded-xl bg-muted/30 animate-pulse"
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
