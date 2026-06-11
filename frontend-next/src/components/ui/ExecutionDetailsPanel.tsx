"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, Clock, Zap } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "./badge";

function fmtMs(ms: number): string {
  return ms < 1000 ? `${Math.round(ms)}ms` : `${(ms / 1000).toFixed(2)}s`;
}

interface ExecutionDetailsPanelProps {
  executionTimeMs: number;
  totalTimeMs: number;
  /** Label for the first row (data/stats execution). Default: "Data execution" */
  executionLabel?: string;
  /** When provided, renders a "Chart type" badge row */
  chartType?: string | null;
}

export function ExecutionDetailsPanel({
  executionTimeMs,
  totalTimeMs,
  executionLabel = "Data execution",
  chartType,
}: ExecutionDetailsPanelProps) {
  const [open, setOpen] = useState(false);
  const llmTimeMs = totalTimeMs - executionTimeMs;

  return (
    <div className="rounded-lg border border-border/40 overflow-hidden text-xs">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls="exec-details-body"
        className={cn(
          "flex w-full items-center justify-between px-3 py-2",
          "text-muted-foreground hover:text-foreground hover:bg-muted/20",
          "transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
        )}
      >
        <div className="flex items-center gap-2">
          <Clock className="h-3 w-3" aria-hidden="true" />
          <span>Execution details</span>
          <span className="text-muted-foreground/60" aria-hidden="true">·</span>
          <span className="font-mono">{(totalTimeMs / 1000).toFixed(1)}s total</span>
        </div>
        <ChevronDown
          className={cn(
            "h-3 w-3 transition-transform duration-200",
            open && "rotate-180"
          )}
          aria-hidden="true"
        />
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            id="exec-details-body"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="border-t border-border/40 px-3 py-3 space-y-2 bg-muted/10">
              {chartType && (
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Chart type</span>
                  <Badge variant="muted" className="text-[10px]">
                    {chartType}
                  </Badge>
                </div>
              )}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5 text-muted-foreground">
                  <Zap className="h-3 w-3" aria-hidden="true" />
                  <span>{executionLabel}</span>
                </div>
                <span className="font-mono text-foreground">{fmtMs(executionTimeMs)}</span>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5 text-muted-foreground">
                  <Clock className="h-3 w-3" aria-hidden="true" />
                  <span>LLM planning</span>
                </div>
                <span className="font-mono text-foreground">{fmtMs(llmTimeMs)}</span>
              </div>
              <div className="flex items-center justify-between border-t border-border/30 pt-2">
                <span className="text-muted-foreground">Total</span>
                <span className="font-mono font-medium text-foreground">
                  {(totalTimeMs / 1000).toFixed(2)}s
                </span>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
