"use client";

import { motion } from "framer-motion";
import { useDatasets } from "@/hooks/use-datasets";
import { DatasetGrid } from "./DatasetGrid";
import { DatasetGridSkeleton } from "./DatasetSkeletons";
import { EmptyState } from "./EmptyState";
import { ErrorState } from "./ErrorState";
import { UploadZone } from "./UploadZone";

export function DatasetsDashboard() {
  const { data, isLoading, isError, error, refetch } = useDatasets();

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      className="space-y-6"
    >
      {/* Upload zone — always visible */}
      <UploadZone />

      {/* Content area */}
      {isLoading ? (
        <DatasetGridSkeleton />
      ) : isError ? (
        <ErrorState
          message={
            error instanceof Error ? error.message : "Failed to load datasets."
          }
          onRetry={() => refetch()}
        />
      ) : data && data.datasets.length > 0 ? (
        <>
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">
              {data.count} dataset{data.count !== 1 ? "s" : ""}
            </p>
          </div>
          <DatasetGrid datasets={data.datasets} />
        </>
      ) : (
        <EmptyState />
      )}
    </motion.div>
  );
}
