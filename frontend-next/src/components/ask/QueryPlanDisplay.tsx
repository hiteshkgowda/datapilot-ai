"use client";

import { ExecutionDetailsPanel } from "@/components/ui/ExecutionDetailsPanel";
import type { ChartType } from "@/lib/api/types";

interface QueryPlanDisplayProps {
  chartType: ChartType | null;
  executionTimeMs: number;
  totalTimeMs: number;
}

export function QueryPlanDisplay({
  chartType,
  executionTimeMs,
  totalTimeMs,
}: QueryPlanDisplayProps) {
  return (
    <ExecutionDetailsPanel
      executionTimeMs={executionTimeMs}
      totalTimeMs={totalTimeMs}
      chartType={chartType}
    />
  );
}
