"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import {
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Lightbulb,
  Loader2,
  Sparkles,
  TrendingUp,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { generateRecommendations } from "@/lib/api/recommendations";
import type {
  AnomalyResponse,
  Recommendation,
  RecommendationCategory,
  RecommendationPriority,
  RecommendationResponse,
} from "@/lib/api/types";

// ---------------------------------------------------------------------------
// Priority styles
// ---------------------------------------------------------------------------

const PRIORITY_CONFIG: Record<
  RecommendationPriority,
  { label: string; className: string; dot: string }
> = {
  critical: {
    label: "Critical",
    className: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
    dot: "bg-red-500",
  },
  high: {
    label: "High",
    className:
      "bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-300",
    dot: "bg-orange-500",
  },
  medium: {
    label: "Medium",
    className:
      "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300",
    dot: "bg-yellow-500",
  },
  low: {
    label: "Low",
    className:
      "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300",
    dot: "bg-blue-500",
  },
};

const CATEGORY_ICONS: Record<RecommendationCategory, React.ElementType> = {
  revenue: TrendingUp,
  operations: Zap,
  inventory: AlertTriangle,
  marketing: Sparkles,
  data_quality: AlertTriangle,
  monitoring: Lightbulb,
  general: Lightbulb,
};

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function PriorityBadge({ priority }: { priority: RecommendationPriority }) {
  const cfg = PRIORITY_CONFIG[priority] ?? PRIORITY_CONFIG.low;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-semibold",
        cfg.className
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", cfg.dot)} />
      {cfg.label}
    </span>
  );
}

function SourceBadge({ source }: { source: string }) {
  const labels: Record<string, string> = {
    anomaly: "Anomaly",
    insight: "Insight",
    forecast: "Forecast",
    cross_signal: "Cross-Signal",
    rule: "Rule",
  };
  return (
    <Badge variant="secondary" className="text-[10px]">
      {labels[source] ?? source}
    </Badge>
  );
}

function RecommendationCard({ rec }: { rec: Recommendation }) {
  const [expanded, setExpanded] = useState(false);
  const CategoryIcon = CATEGORY_ICONS[rec.category] ?? Lightbulb;

  return (
    <div
      className={cn(
        "rounded-lg border border-border/60 bg-card/70 p-4 space-y-2",
        "hover:border-border transition-colors"
      )}
    >
      {/* Header row */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2.5 min-w-0">
          <CategoryIcon className="h-4 w-4 mt-0.5 shrink-0 text-muted-foreground" />
          <p className="text-sm font-medium text-foreground leading-snug">
            {rec.action}
          </p>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <PriorityBadge priority={rec.priority} />
          <SourceBadge source={rec.source} />
        </div>
      </div>

      {/* Confidence bar */}
      <div className="flex items-center gap-2">
        <div className="flex-1 h-1 bg-muted rounded-full overflow-hidden">
          <div
            className="h-full bg-primary/70 rounded-full"
            style={{ width: `${Math.round(rec.confidence * 100)}%` }}
          />
        </div>
        <span className="text-[10px] text-muted-foreground tabular-nums">
          {Math.round(rec.confidence * 100)}% confidence
        </span>
      </div>

      {/* Toggle details */}
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        {expanded ? (
          <ChevronUp className="h-3 w-3" />
        ) : (
          <ChevronDown className="h-3 w-3" />
        )}
        {expanded ? "Hide details" : "Show details"}
      </button>

      {expanded && (
        <div className="space-y-2.5 pt-1 border-t border-border/40">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground mb-0.5">
              Reason
            </p>
            <p className="text-xs text-foreground/80">{rec.reason}</p>
          </div>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground mb-0.5">
              Expected Impact
            </p>
            <p className="text-xs text-foreground/80">{rec.expected_impact}</p>
          </div>
          {rec.data_points.length > 0 && (
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground mb-1">
                Data Points
              </p>
              <ul className="space-y-0.5">
                {rec.data_points.map((dp, i) => (
                  <li
                    key={i}
                    className="text-[10px] font-mono text-muted-foreground bg-muted/50 rounded px-2 py-0.5"
                  >
                    {dp}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Config panel
// ---------------------------------------------------------------------------

interface ConfigPanelProps {
  maxRecs: number;
  llmEnhance: boolean;
  context: string;
  onMaxRecsChange: (v: number) => void;
  onLlmEnhanceChange: (v: boolean) => void;
  onContextChange: (v: string) => void;
}

function ConfigPanel({
  maxRecs,
  llmEnhance,
  context,
  onMaxRecsChange,
  onLlmEnhanceChange,
  onContextChange,
}: ConfigPanelProps) {
  return (
    <div className="rounded-lg border border-border/60 bg-card/60 p-4 space-y-3">
      <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
        Configuration
      </h3>

      <div className="space-y-1">
        <label className="text-xs text-muted-foreground">
          Max recommendations: {maxRecs}
        </label>
        <input
          type="range"
          min={1}
          max={20}
          value={maxRecs}
          onChange={(e) => onMaxRecsChange(Number(e.target.value))}
          className="w-full accent-primary"
        />
      </div>

      <div className="flex items-center justify-between">
        <label className="text-xs text-foreground">LLM enhancement</label>
        <button
          type="button"
          role="switch"
          aria-checked={llmEnhance}
          onClick={() => onLlmEnhanceChange(!llmEnhance)}
          className={cn(
            "relative inline-flex h-5 w-9 items-center rounded-full transition-colors",
            llmEnhance ? "bg-primary" : "bg-muted"
          )}
        >
          <span
            className={cn(
              "inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform",
              llmEnhance ? "translate-x-4" : "translate-x-1"
            )}
          />
        </button>
      </div>

      <div className="space-y-1">
        <label className="text-xs text-muted-foreground">
          Business context (optional)
        </label>
        <textarea
          value={context}
          onChange={(e) => onContextChange(e.target.value)}
          maxLength={1000}
          rows={2}
          placeholder="e.g. Q4 planning cycle, cost reduction initiative…"
          className={cn(
            "w-full rounded-md border border-border/60 bg-background px-2.5 py-1.5",
            "text-xs text-foreground placeholder:text-muted-foreground",
            "focus:outline-none focus:ring-1 focus:ring-primary resize-none"
          )}
        />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Summary bar
// ---------------------------------------------------------------------------

function SummaryBar({ resp }: { resp: RecommendationResponse }) {
  const counts = resp.recommendations.reduce<Record<string, number>>(
    (acc, r) => ({ ...acc, [r.priority]: (acc[r.priority] ?? 0) + 1 }),
    {}
  );

  return (
    <div className="rounded-lg border border-border/60 bg-card/60 p-3 flex flex-wrap gap-3 items-center justify-between">
      <p className="text-xs text-muted-foreground leading-relaxed max-w-xl">
        {resp.summary}
      </p>
      <div className="flex items-center gap-2 shrink-0">
        {(["critical", "high", "medium", "low"] as RecommendationPriority[])
          .filter((p) => counts[p])
          .map((p) => (
            <PriorityBadge key={p} priority={p} />
          ))}
        {resp.llm_enhanced && (
          <Badge variant="secondary" className="gap-1 text-[10px]">
            <Sparkles className="h-2.5 w-2.5" />
            LLM enhanced
          </Badge>
        )}
        {resp.cache_hit && (
          <Badge variant="muted" className="text-[10px]">
            cached
          </Badge>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main workspace
// ---------------------------------------------------------------------------

interface RecommendationWorkspaceProps {
  datasetId: string;
  /** Pre-populated anomaly results from a prior anomaly detection run. */
  anomalies?: AnomalyResponse | null;
}

export function RecommendationWorkspace({
  datasetId,
  anomalies,
}: RecommendationWorkspaceProps) {
  const [maxRecs, setMaxRecs] = useState(10);
  const [llmEnhance, setLlmEnhance] = useState(true);
  const [context, setContext] = useState("");
  const [filterPriority, setFilterPriority] = useState<string>("all");

  const mutation = useMutation({
    mutationFn: () =>
      generateRecommendations({
        dataset_id: datasetId,
        anomalies: anomalies ?? null,
        context: context.trim() || null,
        max_recommendations: maxRecs,
        llm_enhance: llmEnhance,
      }),
  });

  const resp = mutation.data;

  const filteredRecs =
    resp?.recommendations.filter(
      (r) => filterPriority === "all" || r.priority === filterPriority
    ) ?? [];

  return (
    <div className="h-full flex overflow-hidden">
      {/* Left: config */}
      <aside className="w-72 shrink-0 border-r border-border/60 overflow-y-auto p-4 space-y-4">
        <div>
          <h2 className="text-sm font-semibold text-foreground">
            Recommendations
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Transform observations into actions
          </p>
        </div>

        <ConfigPanel
          maxRecs={maxRecs}
          llmEnhance={llmEnhance}
          context={context}
          onMaxRecsChange={setMaxRecs}
          onLlmEnhanceChange={setLlmEnhance}
          onContextChange={setContext}
        />

        {anomalies && (
          <div className="rounded-md bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900/50 p-2.5 text-xs text-amber-800 dark:text-amber-300">
            <AlertTriangle className="inline h-3 w-3 mr-1" />
            {anomalies.total_anomaly_count} anomalies pre-loaded as input
          </div>
        )}

        <Button
          className="w-full"
          onClick={() => mutation.mutate()}
          disabled={mutation.isPending}
        >
          {mutation.isPending ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Generating…
            </>
          ) : (
            <>
              <Lightbulb className="mr-2 h-4 w-4" />
              Generate Recommendations
            </>
          )}
        </Button>

        {mutation.isError && (
          <p className="text-xs text-destructive">
            {(mutation.error as Error)?.message ?? "Generation failed."}
          </p>
        )}
      </aside>

      {/* Right: results */}
      <main className="flex-1 overflow-y-auto p-4 space-y-4">
        {!resp && !mutation.isPending && (
          <div className="flex flex-col items-center justify-center h-full text-center gap-3 text-muted-foreground">
            <Lightbulb className="h-10 w-10 opacity-30" />
            <p className="text-sm">
              Configure inputs and click{" "}
              <span className="font-medium text-foreground">
                Generate Recommendations
              </span>
              .
            </p>
            <p className="text-xs max-w-xs opacity-70">
              The engine analyses anomalies, trends, and forecasts to produce
              prioritised, data-grounded action items.
            </p>
          </div>
        )}

        {mutation.isPending && (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-muted-foreground">
            <Loader2 className="h-8 w-8 animate-spin" />
            <p className="text-sm">Analysing data and generating recommendations…</p>
          </div>
        )}

        {resp && (
          <>
            <SummaryBar resp={resp} />

            {/* Priority filter */}
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs text-muted-foreground">Filter:</span>
              {(["all", "critical", "high", "medium", "low"] as const).map(
                (p) => (
                  <button
                    key={p}
                    onClick={() => setFilterPriority(p)}
                    className={cn(
                      "text-xs rounded-full px-2.5 py-0.5 border transition-colors",
                      filterPriority === p
                        ? "bg-primary text-primary-foreground border-primary"
                        : "border-border/60 text-muted-foreground hover:border-border"
                    )}
                  >
                    {p === "all" ? "All" : PRIORITY_CONFIG[p].label}
                  </button>
                )
              )}
            </div>

            {filteredRecs.length === 0 ? (
              <p className="text-xs text-muted-foreground py-6 text-center">
                No recommendations match the selected filter.
              </p>
            ) : (
              <div className="space-y-3">
                {filteredRecs.map((rec, i) => (
                  <RecommendationCard key={i} rec={rec} />
                ))}
              </div>
            )}

            <p className="text-[10px] text-muted-foreground text-right">
              Generated in {resp.generation_time_ms.toFixed(0)} ms ·{" "}
              {resp.total_count} recommendation(s)
            </p>
          </>
        )}
      </main>
    </div>
  );
}
