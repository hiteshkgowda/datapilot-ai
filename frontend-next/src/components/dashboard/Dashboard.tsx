"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import type { Variants } from "framer-motion";
import {
  ArrowRight,
  Bot,
  Database,
  FileText,
  Link2,
  PenLine,
  TrendingUp,
  Upload,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useDatasets } from "@/hooks/use-datasets";
import { useConnections } from "@/hooks/use-connections";
import { useReports } from "@/hooks/use-reports";
import { useHealth } from "@/hooks/use-health";
import { formatRelativeTime } from "@/lib/format";
import { Skeleton } from "@/components/ui/skeleton";
import type { DatasetMetadata } from "@/lib/api/types";

// ── Animation variants ────────────────────────────────────────────────────────

const containerVariants: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.07 } },
};

const itemVariants: Variants = {
  hidden: { opacity: 0, y: 16 },
  show: { opacity: 1, y: 0, transition: { duration: 0.3, ease: "easeOut" } },
};

// ── KPI Card ──────────────────────────────────────────────────────────────────

interface KpiCardProps {
  label: string;
  value: string | number;
  sub?: string;
  icon: React.ElementType;
  iconColor: string;
  iconBg: string;
  href?: string;
  loading?: boolean;
}

function KpiCard({
  label,
  value,
  sub,
  icon: Icon,
  iconColor,
  iconBg,
  href,
  loading,
}: KpiCardProps) {
  const inner = (
    <div
      className={cn(
        "group rounded-xl border border-border/60 bg-card p-5 space-y-4",
        "elevation-sm transition-all duration-200",
        href && "hover:border-primary/30 hover:elevation-md cursor-pointer"
      )}
    >
      <div className="flex items-start justify-between">
        <div
          className={cn(
            "flex h-9 w-9 items-center justify-center rounded-lg",
            iconBg,
            "transition-transform duration-200 group-hover:scale-105"
          )}
        >
          <Icon className={cn("h-4 w-4", iconColor)} aria-hidden="true" />
        </div>
        {href && (
          <ArrowRight
            className="h-3.5 w-3.5 text-muted-foreground/30 group-hover:text-primary/60 transition-colors"
            aria-hidden="true"
          />
        )}
      </div>

      {loading ? (
        <div className="space-y-2">
          <Skeleton className="h-7 w-16" />
          <Skeleton className="h-3.5 w-24" />
        </div>
      ) : (
        <div>
          <p className="text-2xl font-bold tracking-tight tabular-nums text-foreground">
            {value}
          </p>
          <p className="text-xs text-muted-foreground mt-0.5">{label}</p>
          {sub && (
            <p className="text-[11px] text-muted-foreground/60 mt-1">{sub}</p>
          )}
        </div>
      )}
    </div>
  );

  if (href) {
    return <Link href={href}>{inner}</Link>;
  }
  return inner;
}

// ── Quick action card ─────────────────────────────────────────────────────────

interface ActionCardProps {
  label: string;
  description: string;
  href: string;
  icon: React.ElementType;
  iconColor: string;
  iconBg: string;
}

function ActionCard({
  label,
  description,
  href,
  icon: Icon,
  iconColor,
  iconBg,
}: ActionCardProps) {
  return (
    <Link
      href={href}
      className={cn(
        "group flex items-start gap-3 rounded-xl border border-border/60 bg-card p-4",
        "hover:border-primary/30 hover:bg-card/80 hover:elevation-md",
        "transition-all duration-200",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      )}
    >
      <div
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg mt-0.5",
          iconBg,
          "transition-transform duration-200 group-hover:scale-105"
        )}
      >
        <Icon className={cn("h-3.5 w-3.5", iconColor)} aria-hidden="true" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-foreground group-hover:text-foreground transition-colors">
          {label}
        </p>
        <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
          {description}
        </p>
      </div>
      <ArrowRight
        className="h-3.5 w-3.5 text-muted-foreground/30 group-hover:text-primary/50 mt-0.5 shrink-0 transition-colors"
        aria-hidden="true"
      />
    </Link>
  );
}

// ── Recent dataset row ────────────────────────────────────────────────────────

function RecentDatasetRow({ dataset }: { dataset: DatasetMetadata }) {
  return (
    <Link
      href={`/datasets/${dataset.id}`}
      className={cn(
        "group flex items-center gap-3 rounded-lg px-3 py-2.5",
        "hover:bg-muted/40 transition-colors duration-150",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      )}
    >
      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-primary/10">
        <Database className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-foreground truncate leading-none">
          {dataset.filename}
        </p>
        <p className="text-xs text-muted-foreground mt-0.5">
          {dataset.rows.toLocaleString()} rows · {dataset.columns} cols
        </p>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <span className="text-xs text-muted-foreground/60">
          {formatRelativeTime(dataset.created_at)}
        </span>
        <ArrowRight
          className="h-3 w-3 text-muted-foreground/30 group-hover:text-primary/50 transition-colors"
          aria-hidden="true"
        />
      </div>
    </Link>
  );
}

// ── Main Dashboard ────────────────────────────────────────────────────────────

export function Dashboard() {
  const { data: datasetsData, isLoading: datasetsLoading } = useDatasets();
  const { data: connections, isLoading: connectionsLoading } = useConnections();
  const { data: reportsData, isLoading: reportsLoading } = useReports();
  const { data: health } = useHealth();

  const datasets = datasetsData?.datasets ?? [];
  const recentDatasets = [...datasets]
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    .slice(0, 6);

  // new Date() during render causes hydration mismatch (server clock ≠ client clock).
  // Compute the greeting strings client-side only, after mount.
  const [dayName, setDayName] = useState("");
  const [dateFull, setDateFull] = useState("");
  useEffect(() => {
    const now = new Date();
    setDayName(now.toLocaleDateString("en-US", { weekday: "long" }));
    setDateFull(now.toLocaleDateString("en-US", {
      month: "long",
      day: "numeric",
      year: "numeric",
    }));
  }, []);

  return (
    <motion.div
      variants={containerVariants}
      initial="hidden"
      animate="show"
      className="max-w-5xl space-y-8"
    >
      {/* ── Header ───────────────────────────────────────────────── */}
      <motion.div variants={itemVariants} className="space-y-1">
        <h2 className="text-2xl font-bold tracking-tight text-foreground">
          Welcome back
        </h2>
        <p className="text-sm text-muted-foreground">
          {dayName && dateFull ? `${dayName}, ${dateFull}` : <span className="inline-block h-4 w-48 rounded bg-muted/40 animate-pulse" />}
        </p>
      </motion.div>

      {/* ── KPI Cards ────────────────────────────────────────────── */}
      <motion.div
        variants={itemVariants}
        className="grid grid-cols-2 gap-4 sm:grid-cols-4"
      >
        <KpiCard
          label="Datasets"
          value={datasetsData?.count ?? 0}
          sub={datasets.length > 0 ? `${datasets.filter((d) => d.source === "file").length} files, ${datasets.filter((d) => d.source === "table").length} tables` : "No datasets yet"}
          icon={Database}
          iconColor="text-primary"
          iconBg="bg-primary/10"
          href="/datasets"
          loading={datasetsLoading}
        />
        <KpiCard
          label="Connections"
          value={connections?.length ?? 0}
          sub={connections && connections.length > 0 ? `${[...new Set(connections.map((c) => c.db_type))].join(", ")}` : "No connections yet"}
          icon={Link2}
          iconColor="text-emerald-500"
          iconBg="bg-emerald-500/10"
          href="/connections"
          loading={connectionsLoading}
        />
        <KpiCard
          label="Reports"
          value={reportsData?.count ?? 0}
          sub={
            reportsData && reportsData.count > 0
              ? `${reportsData.reports[0]?.dataset_filename ?? ""}`
              : "No reports yet"
          }
          icon={FileText}
          iconColor="text-amber-500"
          iconBg="bg-amber-500/10"
          href="/reports"
          loading={reportsLoading}
        />
        <KpiCard
          label="Backend"
          value={health?.status === "ok" ? "Online" : "Offline"}
          sub="API status"
          icon={Zap}
          iconColor={
            health?.status === "ok" ? "text-[hsl(var(--success))]" : "text-destructive"
          }
          iconBg={
            health?.status === "ok"
              ? "bg-[hsl(var(--success)/0.1)]"
              : "bg-destructive/10"
          }
        />
      </motion.div>

      {/* ── Two-column: recent datasets + quick actions ───────────── */}
      <div className="grid gap-6 lg:grid-cols-5">
        {/* Recent datasets — 3/5 width */}
        <motion.div variants={itemVariants} className="lg:col-span-3 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-foreground">
              Recent datasets
            </h3>
            <Link
              href="/datasets"
              className="flex items-center gap-1 text-xs text-primary hover:underline transition-opacity"
            >
              View all
              <ArrowRight className="h-3 w-3" aria-hidden="true" />
            </Link>
          </div>

          <div className="rounded-xl border border-border/60 bg-card overflow-hidden">
            {datasetsLoading ? (
              <div className="p-4 space-y-3">
                {[...Array(4)].map((_, i) => (
                  <div key={i} className="flex items-center gap-3">
                    <Skeleton className="h-7 w-7 rounded-md" />
                    <div className="flex-1 space-y-1.5">
                      <Skeleton className="h-3.5 w-3/4" />
                      <Skeleton className="h-3 w-1/2" />
                    </div>
                  </div>
                ))}
              </div>
            ) : recentDatasets.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-10 gap-3">
                <Database className="h-8 w-8 text-muted-foreground/20" />
                <p className="text-sm text-muted-foreground">No datasets yet</p>
                <Link
                  href="/datasets"
                  className="text-xs text-primary hover:underline"
                >
                  Upload your first dataset →
                </Link>
              </div>
            ) : (
              <div className="p-1.5">
                {recentDatasets.map((ds) => (
                  <RecentDatasetRow key={ds.id} dataset={ds} />
                ))}
              </div>
            )}
          </div>
        </motion.div>

        {/* Quick actions — 2/5 width */}
        <motion.div variants={itemVariants} className="lg:col-span-2 space-y-3">
          <h3 className="text-sm font-semibold text-foreground">Quick actions</h3>
          <div className="space-y-2">
            <ActionCard
              label="Upload Dataset"
              description="Import a CSV or Excel file"
              href="/datasets"
              icon={Upload}
              iconColor="text-primary"
              iconBg="bg-primary/10"
            />
            <ActionCard
              label="Generate Report"
              description="Create a PDF analytics report"
              href="/reports"
              icon={FileText}
              iconColor="text-amber-500"
              iconBg="bg-amber-500/10"
            />
            <ActionCard
              label="CRUD Workspace"
              description="Preview and apply data changes"
              href="/crud"
              icon={PenLine}
              iconColor="text-violet-500"
              iconBg="bg-violet-500/10"
            />
            <ActionCard
              label="Run Agent"
              description="Multi-step AI workflow execution"
              href="/agent"
              icon={Bot}
              iconColor="text-emerald-500"
              iconBg="bg-emerald-500/10"
            />
          </div>
        </motion.div>
      </div>

      {/* ── Feature highlights ────────────────────────────────────── */}
      <motion.div variants={itemVariants} className="space-y-3">
        <h3 className="text-sm font-semibold text-foreground">Platform capabilities</h3>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {[
            {
              icon: Database,
              title: "SQL Pushdown",
              desc: "Aggregates run in your database — not in memory. Works on 50M-row tables.",
              color: "text-sky-500",
              bg: "bg-sky-500/10",
            },
            {
              icon: TrendingUp,
              title: "Deterministic Forecast",
              desc: "Holt-Winters, linear trend, or naïve fallback — always disclosed to you.",
              color: "text-emerald-500",
              bg: "bg-emerald-500/10",
            },
            {
              icon: Zap,
              title: "LangGraph Agent",
              desc: "Stateful multi-step agent with approval checkpoints for CRUD ops.",
              color: "text-primary",
              bg: "bg-primary/10",
            },
            {
              icon: Bot,
              title: "QueryPlan Safety",
              desc: "LLM never runs raw SQL. Every query routes through a validated plan.",
              color: "text-amber-500",
              bg: "bg-amber-500/10",
            },
          ].map(({ icon: Icon, title, desc, color, bg }) => (
            <div
              key={title}
              className="rounded-xl border border-border/50 bg-card/60 p-4 space-y-3"
            >
              <div className={cn("flex h-8 w-8 items-center justify-center rounded-lg", bg)}>
                <Icon className={cn("h-3.5 w-3.5", color)} aria-hidden="true" />
              </div>
              <div>
                <p className="text-xs font-semibold text-foreground">{title}</p>
                <p className="text-xs text-muted-foreground mt-1 leading-relaxed">{desc}</p>
              </div>
            </div>
          ))}
        </div>
      </motion.div>
    </motion.div>
  );
}
