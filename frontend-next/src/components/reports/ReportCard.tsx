"use client";

import { motion } from "framer-motion";
import type { Variants } from "framer-motion";
import { Download, FileText, Layers, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { formatBytes, formatRelativeTime } from "@/lib/format";
import { reportDownloadUrl } from "@/lib/api/reports";
import type { ReportMetadata } from "@/lib/api/types";

export const cardVariants: Variants = {
  hidden: { opacity: 0, y: 16 },
  show: { opacity: 1, y: 0, transition: { duration: 0.3 } },
};

interface ReportCardProps {
  report: ReportMetadata;
}

export function ReportCard({ report }: ReportCardProps) {
  const totalSections =
    report.deterministic_section_count + report.ai_section_count;

  return (
    <motion.div
      variants={cardVariants}
      whileHover={{ y: -2, transition: { duration: 0.15 } }}
      className={cn(
        "group relative rounded-xl border border-border/50",
        "bg-card/60 backdrop-blur-sm p-5",
        "hover:border-primary/30 hover:shadow-lg hover:shadow-primary/5",
        "transition-colors duration-200"
      )}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3 mb-4">
        <div className="flex items-center gap-3 min-w-0">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10">
            <FileText className="h-4 w-4 text-primary" aria-hidden="true" />
          </div>
          <div className="min-w-0">
            <p
              className="text-sm font-semibold text-foreground truncate"
              title={report.dataset_filename}
            >
              {report.dataset_filename}
            </p>
            <p className="text-[11px] text-muted-foreground font-mono">
              {report.report_id.slice(0, 8)}…
            </p>
          </div>
        </div>

        <Button
          size="sm"
          variant="ghost"
          className="h-8 shrink-0 text-muted-foreground hover:text-primary hover:bg-primary/5"
          asChild
        >
          <a
            href={reportDownloadUrl(report.report_id)}
            target="_blank"
            rel="noopener noreferrer"
            download={`report_${report.report_id}.pdf`}
            aria-label={`Download report for ${report.dataset_filename}`}
          >
            <Download className="mr-1.5 h-3.5 w-3.5" />
            PDF
          </a>
        </Button>
      </div>

      {/* Section counts */}
      <div className="flex flex-wrap gap-2 mb-4">
        <Badge variant="muted" className="gap-1.5 text-[11px]">
          <Layers className="h-3 w-3" aria-hidden="true" />
          {report.deterministic_section_count} deterministic
        </Badge>
        {report.ai_section_count > 0 && (
          <Badge
            variant="muted"
            className="gap-1.5 text-[11px] text-primary border-primary/20 bg-primary/10"
          >
            <Sparkles className="h-3 w-3" aria-hidden="true" />
            {report.ai_section_count} AI
          </Badge>
        )}
        <Badge variant="muted" className="text-[11px]">
          {totalSections} total
        </Badge>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between text-[11px] text-muted-foreground">
        <span>{formatRelativeTime(report.generated_at)}</span>
        <span>{formatBytes(report.size_bytes)}</span>
      </div>
    </motion.div>
  );
}
