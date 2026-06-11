"use client";

import { motion } from "framer-motion";
import type { Variants } from "framer-motion";
import {
  Activity,
  AlertTriangle,
  BarChart2,
  CalendarDays,
  Database,
  TrendingUp,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { ForecastOperation, Frequency } from "@/lib/api/types";

const FREQ_LABELS: Record<string, string> = {
  D: "Daily",
  W: "Weekly",
  M: "Monthly",
  Q: "Quarterly",
  Y: "Yearly",
};

const OP_CONFIG: Record<
  ForecastOperation,
  { label: string; icon: React.ElementType; color: string }
> = {
  forecast: {
    label: "Forecast",
    icon: TrendingUp,
    color: "text-primary bg-primary/10 border-primary/20",
  },
  anomaly_detection: {
    label: "Anomaly Detection",
    icon: AlertTriangle,
    color: "text-amber-400 bg-amber-400/10 border-amber-400/20",
  },
  timeseries_aggregate: {
    label: "Time Series",
    icon: Activity,
    color: "text-cyan-400 bg-cyan-400/10 border-cyan-400/20",
  },
};

interface MetaCardProps {
  icon: React.ElementType;
  label: string;
  value: React.ReactNode;
  colorClass?: string;
}

function MetaCard({ icon: Icon, label, value, colorClass }: MetaCardProps) {
  return (
    <div className="rounded-xl border border-border/50 bg-card/60 backdrop-blur-sm px-4 py-3 flex items-center gap-3">
      <div
        className={cn(
          "h-8 w-8 rounded-lg flex items-center justify-center shrink-0",
          colorClass ?? "text-muted-foreground bg-muted/30"
        )}
      >
        <Icon className="h-4 w-4" aria-hidden="true" />
      </div>
      <div className="min-w-0">
        <p className="text-[10px] text-muted-foreground uppercase tracking-wide">
          {label}
        </p>
        <p className="text-sm font-semibold text-foreground truncate">{value}</p>
      </div>
    </div>
  );
}

const containerVariants: Variants = {
  hidden: {},
  show: {
    transition: {
      staggerChildren: 0.07,
    },
  },
};

const cardVariants: Variants = {
  hidden: { opacity: 0, y: 16 },
  show: { opacity: 1, y: 0, transition: { duration: 0.35 } },
};

interface ForecastMetaCardsProps {
  operation: ForecastOperation;
  methodUsed: string;
  fallbackUsed: boolean;
  horizon: number;
  frequency: Frequency;
  dataPoints: number;
}

export function ForecastMetaCards({
  operation,
  methodUsed,
  fallbackUsed,
  horizon,
  frequency,
  dataPoints,
}: ForecastMetaCardsProps) {
  const opCfg = OP_CONFIG[operation];

  return (
    <motion.div
      variants={containerVariants}
      initial="hidden"
      animate="show"
      className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5"
    >
      <motion.div variants={cardVariants}>
        <MetaCard
          icon={opCfg.icon}
          label="Operation"
          value={opCfg.label}
          colorClass={opCfg.color}
        />
      </motion.div>

      <motion.div variants={cardVariants}>
        <MetaCard
          icon={BarChart2}
          label="Method"
          value={
            <span className="flex items-center gap-1.5">
              {methodUsed}
              {fallbackUsed && (
                <span
                  className="text-[9px] px-1 rounded bg-amber-400/20 text-amber-400 font-normal"
                  title="Fallback method was used"
                >
                  fallback
                </span>
              )}
            </span>
          }
          colorClass="text-violet-400 bg-violet-400/10"
        />
      </motion.div>

      <motion.div variants={cardVariants}>
        <MetaCard
          icon={TrendingUp}
          label="Horizon"
          value={horizon > 0 ? `${horizon} period${horizon !== 1 ? "s" : ""}` : "—"}
          colorClass="text-emerald-400 bg-emerald-400/10"
        />
      </motion.div>

      <motion.div variants={cardVariants}>
        <MetaCard
          icon={CalendarDays}
          label="Frequency"
          value={FREQ_LABELS[frequency] ?? frequency}
          colorClass="text-sky-400 bg-sky-400/10"
        />
      </motion.div>

      <motion.div variants={cardVariants} className="col-span-2 sm:col-span-1">
        <MetaCard
          icon={Database}
          label="Data Points"
          value={dataPoints.toLocaleString()}
          colorClass="text-rose-400 bg-rose-400/10"
        />
      </motion.div>
    </motion.div>
  );
}
