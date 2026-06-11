"use client";

import Link from "next/link";
import { motion, type Variants } from "framer-motion";
import {
  Database,
  FileSpreadsheet,
  FileText,
  ArrowRight,
  Table2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { formatBytes, formatNumber, formatRelativeTime } from "@/lib/format";
import type { DatasetMetadata } from "@/lib/api/types";

function DatasetIcon({
  source,
  fileType,
  className,
}: {
  source: DatasetMetadata["source"];
  fileType: DatasetMetadata["file_type"];
  className?: string;
}) {
  if (source === "table") {
    return <Database className={className} />;
  }
  if (fileType === "excel") {
    return <FileSpreadsheet className={className} />;
  }
  return <FileText className={className} />;
}

function sourceLabel(ds: DatasetMetadata): string {
  if (ds.source === "table") return "DB table";
  return ds.file_type === "excel" ? "Excel" : "CSV";
}

// Typed as Variants so TypeScript resolves `ease` as the Easing union, not string
export const cardVariants: Variants = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0 },
};

interface DatasetCardProps {
  dataset: DatasetMetadata;
}

export function DatasetCard({ dataset }: DatasetCardProps) {
  return (
    <motion.div
      variants={cardVariants}
      transition={{ duration: 0.28, ease: "easeOut" }}
    >
      <Link
        href={`/datasets/${dataset.id}`}
        className={cn(
          "group block rounded-xl border border-border/60 bg-card/60",
          "backdrop-blur-sm p-5 space-y-4",
          "hover:border-primary/40 hover:bg-card/80 hover:shadow-lg hover:shadow-primary/5",
          "transition-all duration-200",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        )}
      >
        {/* Header row */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <div
              className={cn(
                "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg",
                "bg-primary/10 text-primary",
                "group-hover:bg-primary/15 transition-colors"
              )}
            >
              <DatasetIcon
                source={dataset.source}
                fileType={dataset.file_type}
                className="h-4 w-4"
              />
            </div>
            <div className="min-w-0">
              <p
                className="text-sm font-semibold leading-snug truncate text-foreground"
                title={dataset.filename}
              >
                {dataset.filename}
              </p>
              <p className="text-xs text-muted-foreground mt-0.5">
                {formatRelativeTime(dataset.created_at)}
              </p>
            </div>
          </div>
          <Badge variant="muted" className="shrink-0">
            {sourceLabel(dataset)}
          </Badge>
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-3 gap-2">
          {[
            { label: "Rows", value: formatNumber(dataset.rows) },
            { label: "Cols", value: String(dataset.columns) },
            {
              label: "Size",
              value:
                dataset.source === "table" ? "—" : formatBytes(dataset.size_bytes),
            },
          ].map(({ label, value }) => (
            <div
              key={label}
              className="rounded-lg bg-muted/40 px-3 py-2 text-center"
            >
              <p className="text-xs text-muted-foreground">{label}</p>
              <p className="text-sm font-medium font-mono text-foreground mt-0.5">
                {value}
              </p>
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between">
          {dataset.truncated && (
            <span className="flex items-center gap-1 text-xs text-warning">
              <Table2 className="h-3 w-3" />
              Row-limited
            </span>
          )}
          <span
            className={cn(
              "ml-auto flex items-center gap-1 text-xs font-medium text-primary",
              "opacity-0 group-hover:opacity-100 transition-opacity duration-150"
            )}
          >
            View dataset
            <ArrowRight className="h-3 w-3" />
          </span>
        </div>
      </Link>
    </motion.div>
  );
}
