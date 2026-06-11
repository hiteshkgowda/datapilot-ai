"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useDatasetPreview } from "@/hooks/use-datasets";
import { MetaPanel } from "./MetaPanel";
import { PreviewTable } from "./PreviewTable";
import { DatasetDetailSkeleton } from "./DatasetSkeletons";
import { ErrorState } from "./ErrorState";

interface DatasetDetailViewProps {
  id: string;
}

export function DatasetDetailView({ id }: DatasetDetailViewProps) {
  const { data, isLoading, isError, error, refetch } = useDatasetPreview(id);

  if (isLoading) return <DatasetDetailSkeleton />;

  if (isError) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" size="sm" asChild>
          <Link href="/datasets">
            <ArrowLeft className="mr-1.5 h-4 w-4" />
            Datasets
          </Link>
        </Button>
        <ErrorState
          message={
            error instanceof Error ? error.message : "Failed to load dataset."
          }
          onRetry={() => refetch()}
        />
      </div>
    );
  }

  if (!data) return null;

  // Build a DatasetMetadata-compatible object from the preview response
  // (preview is a superset of metadata in the fields we need for MetaPanel)
  const meta = {
    id: data.id,
    filename: data.filename,
    source: data.source,
    file_type: data.file_type,
    size_bytes: 0,
    rows: data.rows,
    columns: data.columns,
    column_names: data.column_names,
    created_at: new Date().toISOString(), // not in preview; shows N/A via relative time
    connection_id: null,
    db_schema: null,
    table_name: null,
    row_limit: null,
    truncated: null,
    estimated_row_count: null,
    db_columns: null,
  } as const;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      className="space-y-6"
    >
      {/* Page header */}
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" asChild className="-ml-2">
          <Link href="/datasets">
            <ArrowLeft className="mr-1.5 h-4 w-4" />
            Datasets
          </Link>
        </Button>
      </div>

      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground truncate">
          {data.filename}
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          {data.rows.toLocaleString()} rows · {data.columns} columns
          {data.file_type && ` · ${data.file_type.toUpperCase()}`}
        </p>
      </div>

      {/* Two-column layout: meta panel + preview table */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[300px_1fr] items-start">
        <MetaPanel dataset={meta} />
        <PreviewTable preview={data} />
      </div>
    </motion.div>
  );
}
