"use client";

import Link from "next/link";
import {
  Activity,
  AlertTriangle,
  BarChart2,
  Bot,
  Calendar,
  Database,
  FileSpreadsheet,
  FileText,
  GitBranch,
  Layers,
  Lightbulb,
  Rows3,
  TrendingUp,
  FileOutput,
  HardDrive,
  LayoutDashboard,
  Search,
  ShieldCheck,
  Sparkles,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Button } from "@/components/ui/button";
import {
  formatBytes,
  formatNumber,
  formatRelativeTime,
} from "@/lib/format";
import type { DatasetMetadata } from "@/lib/api/types";

interface MetaRowProps {
  icon: React.ElementType;
  label: string;
  value: string;
}

function MetaRow({ icon: Icon, label, value }: MetaRowProps) {
  return (
    <div className="flex items-center justify-between gap-4 py-1">
      <div className="flex items-center gap-2 text-xs text-muted-foreground min-w-0">
        <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        <span>{label}</span>
      </div>
      <span className="text-xs font-medium font-mono text-foreground truncate">
        {value}
      </span>
    </div>
  );
}

interface QuickAction {
  href: string;
  icon: React.ElementType;
  label: string;
  disabled?: boolean;
  disabledReason?: string;
}

interface MetaPanelProps {
  dataset: DatasetMetadata;
}

export function MetaPanel({ dataset }: MetaPanelProps) {
  const sourceIcon =
    dataset.source === "table"
      ? Database
      : dataset.file_type === "excel"
      ? FileSpreadsheet
      : FileText;

  const sourceLabel =
    dataset.source === "table"
      ? `${dataset.db_schema ? dataset.db_schema + "." : ""}${dataset.table_name ?? "table"}`
      : dataset.file_type === "excel"
      ? "Excel"
      : "CSV";

  const quickActions: QuickAction[] = [
    {
      href: `/datasets/${dataset.id}/analysis`,
      icon: Zap,
      label: "Autonomous Analysis",
    },
    {
      href: `/datasets/${dataset.id}/quality`,
      icon: ShieldCheck,
      label: "Data Quality",
    },
    {
      href: `/datasets/${dataset.id}/monitor`,
      icon: Activity,
      label: "KPI Monitor",
    },
    {
      href: `/datasets/${dataset.id}/ask`,
      icon: BarChart2,
      label: "Ask Data",
    },
    {
      href: `/datasets/${dataset.id}/forecast`,
      icon: TrendingUp,
      label: "Forecast",
    },
    {
      href: `/datasets/${dataset.id}/reports`,
      icon: FileOutput,
      label: "Generate Report",
    },
    {
      href: `/datasets/${dataset.id}/anomalies`,
      icon: AlertTriangle,
      label: "Detect Anomalies",
    },
    {
      href: `/datasets/${dataset.id}/recommendations`,
      icon: Lightbulb,
      label: "Recommendations",
    },
    {
      href: `/datasets/${dataset.id}/insights`,
      icon: Sparkles,
      label: "AI Insights",
    },
    {
      href: `/datasets/${dataset.id}/root-cause`,
      icon: Search,
      label: "Root Cause",
    },
    {
      href: `/datasets/${dataset.id}/dashboard`,
      icon: LayoutDashboard,
      label: "Executive Dashboard",
    },
    {
      href: `/agent?dataset=${dataset.id}`,
      icon: Bot,
      label: "AI Agent",
    },
  ];

  return (
    <div
      className={cn(
        "rounded-xl border border-border/60 bg-card/60 backdrop-blur-sm",
        "p-5 space-y-4 h-fit"
      )}
    >
      {/* Title */}
      <div>
        <h2 className="text-sm font-semibold text-foreground">Metadata</h2>
      </div>

      {/* Key stats */}
      <div className="space-y-0.5">
        <MetaRow icon={Rows3} label="Rows" value={formatNumber(dataset.rows)} />
        <MetaRow icon={Layers} label="Columns" value={String(dataset.columns)} />
        {dataset.source === "file" && (
          <MetaRow icon={HardDrive} label="Size" value={formatBytes(dataset.size_bytes)} />
        )}
        <MetaRow icon={sourceIcon} label="Source" value={sourceLabel} />
        <MetaRow
          icon={Calendar}
          label="Created"
          value={formatRelativeTime(dataset.created_at)}
        />
        {dataset.truncated && (
          <MetaRow
            icon={Rows3}
            label="Total rows"
            value={
              dataset.estimated_row_count
                ? `~${formatNumber(dataset.estimated_row_count)}`
                : "unknown"
            }
          />
        )}
      </div>

      <Separator />

      {/* Column name chips */}
      <div>
        <p className="mb-2 text-xs text-muted-foreground">Columns</p>
        <div className="flex flex-wrap gap-1.5" role="list" aria-label="Column names">
          {dataset.column_names.map((col) => (
            <Badge key={col} variant="muted" role="listitem">
              {col}
            </Badge>
          ))}
        </div>
      </div>

      <Separator />

      {/* Quick actions */}
      <div className="space-y-2">
        <p className="text-xs text-muted-foreground">Quick actions</p>
        {quickActions.map(({ href, icon: Icon, label, disabled, disabledReason }) =>
          disabled ? (
            <Button
              key={label}
              variant="ghost"
              size="sm"
              className="w-full justify-start text-muted-foreground cursor-not-allowed"
              disabled
              title={disabledReason}
            >
              <Icon className="mr-2 h-4 w-4" />
              {label}
            </Button>
          ) : (
            <Button
              key={label}
              variant="ghost"
              size="sm"
              className="w-full justify-start text-foreground hover:text-primary hover:bg-primary/5"
              asChild
            >
              <Link href={href}>
                <Icon className="mr-2 h-4 w-4" />
                {label}
              </Link>
            </Button>
          )
        )}
      </div>
    </div>
  );
}
