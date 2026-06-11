"use client";

import { useState } from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import type { Variants } from "framer-motion";
import { ArrowLeft, RotateCcw, TrendingUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useForecast } from "@/hooks/use-forecast";
import { useDatasetPreview } from "@/hooks/use-datasets";
import { ForecastForm } from "./ForecastForm";
import { ForecastResult } from "./ForecastResult";
import type { ForecastResponse } from "@/lib/api/types";

const pageVariants: Variants = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { duration: 0.3 } },
};

function LoadingSkeleton() {
  return (
    <div className="space-y-6 animate-pulse">
      {/* Answer skeleton */}
      <div className="rounded-xl border border-border/30 bg-card/40 px-5 py-4 space-y-2">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-4/5" />
        <Skeleton className="h-4 w-3/5" />
      </div>
      {/* Meta cards skeleton */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <div
            key={i}
            className="rounded-xl border border-border/30 bg-card/40 px-4 py-3 flex items-center gap-3"
          >
            <Skeleton className="h-8 w-8 rounded-lg shrink-0" />
            <div className="space-y-1.5 flex-1">
              <Skeleton className="h-2 w-12" />
              <Skeleton className="h-4 w-20" />
            </div>
          </div>
        ))}
      </div>
      {/* Chart skeleton */}
      <div className="rounded-xl border border-border/30 bg-card/40 p-4">
        <Skeleton className="h-72 w-full rounded-lg" />
      </div>
    </div>
  );
}

interface ForecastWorkspaceProps {
  datasetId: string;
}

export function ForecastWorkspace({ datasetId }: ForecastWorkspaceProps) {
  const { data: preview } = useDatasetPreview(datasetId);
  const { mutate, isPending, error, reset } = useForecast();
  const [result, setResult] = useState<ForecastResponse | null>(null);

  const filename = preview?.filename ?? "this dataset";

  function handleSubmit(question: string) {
    // Clear previous result before new run
    setResult(null);
    mutate(
      { datasetId, question },
      {
        onSuccess: (data) => setResult(data),
      }
    );
  }

  function handleClear() {
    setResult(null);
    reset();
  }

  return (
    <motion.div
      variants={pageVariants}
      initial="hidden"
      animate="show"
      className="mx-auto max-w-4xl space-y-6"
    >
      {/* Page header */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3 min-w-0">
          <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0" asChild>
            <Link href={`/datasets/${datasetId}`} aria-label="Back to dataset">
              <ArrowLeft className="h-4 w-4" />
            </Link>
          </Button>
          <div>
            <div className="flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/10">
                <TrendingUp className="h-4 w-4 text-primary" aria-hidden="true" />
              </div>
              <h1 className="text-lg font-semibold text-foreground">Forecast</h1>
            </div>
            <p className="text-sm text-muted-foreground truncate max-w-[300px]">
              {filename}
            </p>
          </div>
        </div>

        {result && (
          <Button
            variant="ghost"
            size="sm"
            className="text-muted-foreground hover:text-foreground shrink-0"
            onClick={handleClear}
            title="Clear results"
          >
            <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
            Clear
          </Button>
        )}
      </div>

      {/* Form */}
      <ForecastForm
        onSubmit={handleSubmit}
        isPending={isPending}
        hasResult={result !== null}
      />

      {/* Result area */}
      <AnimatePresence mode="wait">
        {isPending && (
          <motion.div
            key="loading"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            <LoadingSkeleton />
          </motion.div>
        )}

        {error && !isPending && !result && (
          <motion.div
            key="error"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="rounded-xl border border-destructive/30 bg-destructive/5 px-5 py-4"
          >
            <p className="text-sm font-medium text-destructive mb-1">Forecast failed</p>
            <p className="text-xs text-muted-foreground">{error.message}</p>
          </motion.div>
        )}

        {result && !isPending && (
          <motion.div
            key="result"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            <ForecastResult result={result} />
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
