"use client";

import { motion } from "framer-motion";
import type { Variants } from "framer-motion";
import { PlotlyChart } from "@/components/ask/PlotlyChart";
import { ResultTable } from "@/components/ask/ResultTable";
import { ExecutionDetailsPanel } from "@/components/ui/ExecutionDetailsPanel";
import { ForecastMetaCards } from "./ForecastMetaCards";
import type { ForecastResponse } from "@/lib/api/types";

const sectionVariants: Variants = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0, transition: { duration: 0.4 } },
};

interface ForecastResultProps {
  result: ForecastResponse;
}

export function ForecastResult({ result }: ForecastResultProps) {
  return (
    <motion.div
      variants={sectionVariants}
      initial="hidden"
      animate="show"
      className="space-y-6"
    >
      {/* Answer */}
      <div className="rounded-xl border border-primary/20 bg-primary/5 px-5 py-4">
        <p className="text-sm leading-relaxed text-foreground">{result.answer}</p>
      </div>

      {/* Metadata cards */}
      <ForecastMetaCards
        operation={result.operation}
        methodUsed={result.method_used}
        fallbackUsed={result.fallback_used}
        horizon={result.horizon}
        frequency={result.frequency}
        dataPoints={result.data_points}
      />

      {/* Chart */}
      {result.chart_spec && (
        <motion.div
          initial={{ opacity: 0, scale: 0.98 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5, delay: 0.2 }}
          className="rounded-xl border border-border/50 bg-card/60 backdrop-blur-sm p-4"
        >
          <PlotlyChart spec={result.chart_spec} />
        </motion.div>
      )}

      {/* Table */}
      {result.table_data.length > 0 && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.4, delay: 0.35 }}
        >
          <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Data table
          </h3>
          <ResultTable data={result.table_data} />
        </motion.div>
      )}

      {/* Execution details */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.3, delay: 0.5 }}
      >
        <ExecutionDetailsPanel
          executionTimeMs={result.execution_time_ms}
          totalTimeMs={result.total_time_ms}
          executionLabel="Statistics engine"
        />
      </motion.div>
    </motion.div>
  );
}
