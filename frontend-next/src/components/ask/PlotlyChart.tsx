"use client";

import dynamic from "next/dynamic";
import type { PlotParams } from "react-plotly.js";
import { Skeleton } from "@/components/ui/skeleton";

// Plotly is ~3.5 MB — lazy-load so it doesn't bloat the initial bundle.
const Plot = dynamic<PlotParams>(() => import("react-plotly.js"), {
  ssr: false,
  loading: () => <Skeleton className="h-72 w-full rounded-lg" />,
});

/**
 * Dark-mode overrides that blend with the blue-black card surfaces.
 * Grid lines use the new --border hue; colorway matches the design system.
 */
const DARK_LAYOUT_OVERRIDES: Partial<Plotly.Layout> = {
  paper_bgcolor: "transparent",
  plot_bgcolor: "transparent",
  font: {
    color: "hsl(215, 16%, 50%)",
    size: 11,
    family: "var(--font-sans, Inter, system-ui, sans-serif)",
  },
  xaxis: {
    gridcolor: "hsl(228, 16%, 16%)",
    linecolor: "hsl(228, 16%, 16%)",
    zerolinecolor: "hsl(228, 16%, 16%)",
    tickfont: { color: "hsl(215, 16%, 44%)", size: 10 },
  },
  yaxis: {
    gridcolor: "hsl(228, 16%, 16%)",
    linecolor: "hsl(228, 16%, 16%)",
    zerolinecolor: "hsl(228, 16%, 16%)",
    tickfont: { color: "hsl(215, 16%, 44%)", size: 10 },
  },
  legend: {
    font: { color: "hsl(215, 16%, 50%)", size: 11 },
    bgcolor: "transparent",
    borderwidth: 0,
  },
  title: { font: { color: "hsl(210, 40%, 97%)", size: 13 }, pad: { t: 4 } },
  margin: { t: 36, r: 12, b: 44, l: 52, pad: 2 },
  // Brand-adjacent colorway: indigo → cyan → amber → emerald → pink → orange
  colorway: [
    "#6366f1",
    "#06b6d4",
    "#f59e0b",
    "#22c55e",
    "#ec4899",
    "#f97316",
    "#8b5cf6",
    "#14b8a6",
  ],
};

interface PlotlyChartProps {
  spec: Record<string, unknown>;
}

export function PlotlyChart({ spec }: PlotlyChartProps) {
  const data = (spec.data ?? []) as Plotly.Data[];
  const layout: Partial<Plotly.Layout> = {
    ...(spec.layout as Partial<Plotly.Layout>),
    ...DARK_LAYOUT_OVERRIDES,
  };
  const config: Partial<Plotly.Config> = {
    displayModeBar: false,
    responsive: true,
    scrollZoom: false,
  };

  return (
    <div className="w-full overflow-hidden">
      <Plot
        data={data}
        layout={layout}
        config={config}
        style={{ width: "100%", height: "320px" }}
        useResizeHandler
      />
    </div>
  );
}
