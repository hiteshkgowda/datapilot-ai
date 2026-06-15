"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import type { Variants } from "framer-motion";
import {
  BarChart2,
  CalendarDays,
  ChevronRight,
  LayoutDashboard,
  Loader2,
  Plus,
  Sparkles,
  X,
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { listDashboards, generateDashboard, saveDashboard } from "@/lib/api/dashboards";
import { listDatasets } from "@/lib/api/datasets";
import type { DashboardConfig } from "@/lib/api/types";
import { formatRelativeTime } from "@/lib/format";

const fadeUp: Variants = {
  hidden: { opacity: 0, y: 10 },
  show: { opacity: 1, y: 0, transition: { duration: 0.2 } },
};

const stagger: Variants = {
  show: { transition: { staggerChildren: 0.05 } },
};

// ─── Create modal ─────────────────────────────────────────────────────────────

interface CreateModalProps {
  onClose: () => void;
}

function CreateModal({ onClose }: CreateModalProps) {
  const router = useRouter();
  const [datasetId, setDatasetId] = useState("");
  const [prompt, setPrompt] = useState(
    "Create an executive overview dashboard with key performance indicators and trend charts."
  );

  const { data: datasetsResp, isLoading: datasetsLoading } = useQuery({
    queryKey: ["datasets-list"],
    queryFn: listDatasets,
    staleTime: 30_000,
  });

  const createMutation = useMutation({
    mutationFn: async () => {
      const generated = await generateDashboard({
        dataset_id: datasetId,
        prompt,
        max_kpis: 8,
        max_charts: 4,
      });
      const config: DashboardConfig = {
        dashboard_id: null,
        dashboard_name: generated.dashboard_name,
        dataset_id: generated.dataset_id,
        owner_sub: "",
        kpis: generated.kpis,
        charts: generated.charts,
        layout: generated.layout,
        recommendations: generated.recommendations,
        score: generated.score,
        generation_time_ms: generated.generation_time_ms,
        cache_hit: generated.cache_hit,
        created_at: new Date().toISOString(),
      };
      return saveDashboard({ dashboard_config: config });
    },
    onSuccess: (data) => {
      toast.success("Dashboard created");
      router.push(`/dashboards/${data.dashboard_id}`);
    },
    onError: (err: Error) => {
      toast.error(`Failed: ${err.message}`);
    },
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: 8 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96 }}
        transition={{ duration: 0.18 }}
        className="w-full max-w-md rounded-2xl border border-border/60 bg-card shadow-2xl p-6 space-y-5"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10">
              <LayoutDashboard className="h-4 w-4 text-primary" />
            </div>
            <h2 className="text-base font-semibold text-foreground">
              New Dashboard
            </h2>
          </div>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-foreground">
              Dataset
            </label>
            {datasetsLoading ? (
              <div className="h-9 rounded-lg bg-muted/40 animate-pulse" />
            ) : (
              <select
                value={datasetId}
                onChange={(e) => setDatasetId(e.target.value)}
                className={cn(
                  "w-full rounded-lg border border-border/60 bg-card/60 px-3 py-2",
                  "text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/30"
                )}
              >
                <option value="">Select a dataset…</option>
                {datasetsResp?.datasets.map((ds) => (
                  <option key={ds.id} value={ds.id}>
                    {ds.filename}
                  </option>
                ))}
              </select>
            )}
          </div>

          <div className="space-y-1.5">
            <label className="text-sm font-medium text-foreground">
              Prompt
            </label>
            <textarea
              rows={3}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              className={cn(
                "w-full resize-none rounded-lg border border-border/60 bg-card/60 px-3 py-2.5",
                "text-sm text-foreground placeholder:text-muted-foreground/50",
                "focus:outline-none focus:ring-2 focus:ring-primary/30 transition-colors"
              )}
            />
          </div>
        </div>

        <div className="flex gap-3 pt-1">
          <Button variant="outline" className="flex-1" onClick={onClose}>
            Cancel
          </Button>
          <Button
            className="flex-1"
            disabled={!datasetId || !prompt.trim() || createMutation.isPending}
            onClick={() => createMutation.mutate()}
          >
            {createMutation.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Sparkles className="mr-2 h-4 w-4" />
            )}
            {createMutation.isPending ? "Generating…" : "Generate & Save"}
          </Button>
        </div>
      </motion.div>
    </div>
  );
}

// ─── Dashboard card ───────────────────────────────────────────────────────────

function DashboardCard({
  id,
  name,
  score,
  createdAt,
}: {
  id: string;
  name: string;
  score: number;
  createdAt: string;
}) {
  return (
    <motion.div variants={fadeUp}>
      <Link
        href={`/dashboards/${id}`}
        className={cn(
          "group flex items-start justify-between gap-4 rounded-xl border border-border/60 bg-card/70 p-4",
          "hover:border-primary/40 hover:bg-primary/5 transition-all duration-150"
        )}
      >
        <div className="flex items-start gap-3 min-w-0">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 mt-0.5">
            <BarChart2 className="h-4 w-4 text-primary" />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-medium text-foreground truncate group-hover:text-primary transition-colors">
              {name}
            </p>
            <div className="flex items-center gap-3 mt-1">
              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                <CalendarDays className="h-3 w-3" />
                {formatRelativeTime(createdAt)}
              </div>
              <div className="text-xs text-muted-foreground">
                Score {Math.round(score * 100)}%
              </div>
            </div>
          </div>
        </div>
        <ChevronRight className="h-4 w-4 text-muted-foreground/40 group-hover:text-primary/60 shrink-0 mt-2.5 transition-colors" />
      </Link>
    </motion.div>
  );
}

// ─── DashboardHub ─────────────────────────────────────────────────────────────

export function DashboardHub() {
  const [showCreate, setShowCreate] = useState(false);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["dashboards-list"],
    queryFn: listDashboards,
    staleTime: 30_000,
  });

  const dashboards = data?.dashboards ?? [];

  return (
    <>
      {showCreate && <CreateModal onClose={() => setShowCreate(false)} />}

      <div className="max-w-3xl mx-auto px-6 py-8 space-y-8">
        {/* header */}
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10">
              <LayoutDashboard className="h-5 w-5 text-primary" />
            </div>
            <div>
              <h1 className="text-xl font-semibold text-foreground">
                Dashboards
              </h1>
              <p className="text-sm text-muted-foreground">
                {dashboards.length} saved dashboard
                {dashboards.length !== 1 ? "s" : ""}
              </p>
            </div>
          </div>
          <Button onClick={() => setShowCreate(true)}>
            <Plus className="mr-2 h-4 w-4" />
            New Dashboard
          </Button>
        </div>

        {/* list */}
        {isLoading ? (
          <div className="space-y-3">
            {[...Array(3)].map((_, i) => (
              <div
                key={i}
                className="h-[72px] rounded-xl bg-muted/30 animate-pulse"
              />
            ))}
          </div>
        ) : isError ? (
          <div className="rounded-xl border border-border/60 bg-card/60 p-8 text-center space-y-3">
            <p className="text-sm text-muted-foreground">
              Failed to load dashboards
            </p>
            <Button variant="outline" size="sm" onClick={() => refetch()}>
              Retry
            </Button>
          </div>
        ) : dashboards.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border/60 bg-card/40 p-12 text-center space-y-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-muted/40 mx-auto">
              <LayoutDashboard className="h-6 w-6 text-muted-foreground/60" />
            </div>
            <div className="space-y-1">
              <p className="text-sm font-medium text-foreground">
                No dashboards yet
              </p>
              <p className="text-sm text-muted-foreground">
                Generate a dashboard from any dataset to get started
              </p>
            </div>
            <Button onClick={() => setShowCreate(true)}>
              <Plus className="mr-2 h-4 w-4" />
              Create your first dashboard
            </Button>
          </div>
        ) : (
          <motion.div
            variants={stagger}
            initial="hidden"
            animate="show"
            className="space-y-3"
          >
            {dashboards.map((d) => (
              <DashboardCard
                key={d.dashboard_id}
                id={d.dashboard_id}
                name={d.dashboard_name}
                score={d.score}
                createdAt={d.created_at}
              />
            ))}
          </motion.div>
        )}
      </div>
    </>
  );
}
