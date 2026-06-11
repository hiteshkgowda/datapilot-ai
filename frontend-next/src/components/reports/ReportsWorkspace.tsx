"use client";

import { motion, AnimatePresence } from "framer-motion";
import type { Variants } from "framer-motion";
import { FileText } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { useReports } from "@/hooks/use-reports";
import { ReportCard, cardVariants } from "./ReportCard";
import { ReportGenerateForm } from "./ReportGenerateForm";

const gridVariants: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.07 } },
};

function ReportGridSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: 3 }).map((_, i) => (
        <div
          key={i}
          className="rounded-xl border border-border/30 bg-card/40 p-5 space-y-4"
        >
          <div className="flex items-center gap-3">
            <Skeleton className="h-9 w-9 rounded-lg shrink-0" />
            <div className="space-y-1.5 flex-1">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-3 w-16" />
            </div>
          </div>
          <div className="flex gap-2">
            <Skeleton className="h-5 w-28 rounded-full" />
            <Skeleton className="h-5 w-16 rounded-full" />
          </div>
          <div className="flex justify-between">
            <Skeleton className="h-3 w-20" />
            <Skeleton className="h-3 w-12" />
          </div>
        </div>
      ))}
    </div>
  );
}

interface ReportsWorkspaceProps {
  defaultDatasetId?: string;
}

export function ReportsWorkspace({ defaultDatasetId }: ReportsWorkspaceProps) {
  const { data, isLoading } = useReports();
  const reports = data?.reports ?? [];

  // Filter to dataset if pre-selected
  const filtered = defaultDatasetId
    ? reports.filter((r) => r.dataset_id === defaultDatasetId)
    : reports;

  return (
    <div className="mx-auto max-w-5xl space-y-8">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10">
          <FileText className="h-5 w-5 text-primary" aria-hidden="true" />
        </div>
        <div>
          <h1 className="text-lg font-semibold text-foreground">Reports</h1>
          <p className="text-sm text-muted-foreground">
            Generate and download PDF analytics reports
          </p>
        </div>
      </div>

      {/* Generate form */}
      <ReportGenerateForm defaultDatasetId={defaultDatasetId} />

      {/* Report list */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-foreground">
            {defaultDatasetId ? "Reports for this dataset" : "All reports"}
          </h2>
          {data && (
            <span className="text-xs text-muted-foreground">
              {filtered.length} report{filtered.length !== 1 ? "s" : ""}
            </span>
          )}
        </div>

        {isLoading ? (
          <ReportGridSkeleton />
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border/50 bg-card/20 py-16 text-center">
            <FileText
              className="mb-3 h-10 w-10 text-muted-foreground/30"
              aria-hidden="true"
            />
            <p className="text-sm font-medium text-muted-foreground">
              No reports yet
            </p>
            <p className="mt-1 text-xs text-muted-foreground/60">
              Generate a report above to get started
            </p>
          </div>
        ) : (
          <AnimatePresence>
            <motion.div
              variants={gridVariants}
              initial="hidden"
              animate="show"
              className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
            >
              {filtered.map((report) => (
                <motion.div key={report.report_id} variants={cardVariants}>
                  <ReportCard report={report} />
                </motion.div>
              ))}
            </motion.div>
          </AnimatePresence>
        )}
      </div>
    </div>
  );
}
