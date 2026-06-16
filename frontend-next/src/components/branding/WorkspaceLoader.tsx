"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import { motion, AnimatePresence, type Variants } from "framer-motion";
import {
  CheckCircle2,
  Circle,
  BarChart3,
  TrendingUp,
  Lightbulb,
  Network,
  FileText,
  Activity,
  Database,
  Search,
  GitBranch,
  Sparkles,
  CheckCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";

// ─────────────────────────────────────────────────────────────────────────────
// Constants — all colors hard-coded (this screen is always dark)
// ─────────────────────────────────────────────────────────────────────────────

const BG        = "#0f1e16";
const EMERALD   = "rgb(52,211,153)";
const E_DIM     = "rgba(52,211,153,0.18)";

// Startup sequence steps with completion timestamps (ms)
const STARTUP_STEPS = [
  { label: "Workspace authenticated",    completeAt: 500  },
  { label: "User profile loaded",        completeAt: 920  },
  { label: "Analytics engine online",    completeAt: 1300 },
  { label: "Forecasting engine online",  completeAt: 1660 },
  { label: "Insight generation ready",   completeAt: 1990 },
  { label: "Root cause analysis ready",  completeAt: 2290 },
  { label: "Recommendation engine ready",completeAt: 2570 },
  { label: "Executive reporting ready",  completeAt: 2820 },
  { label: "Agent orchestration online", completeAt: 3050 },
] as const;

const READY_AT    = 3300;  // ms — "Workspace Ready" appears
const EXITING_AT  = 4650;  // ms — fade-to-dark overlay starts
// router.replace fires via onAnimationComplete ~300ms after EXITING_AT ≈ 5000ms

// System status cards
const SYSTEM_SERVICES = [
  { label: "Analytics Engine",  icon: BarChart3,  onlineAtStep: 3 },
  { label: "Forecast Engine",   icon: TrendingUp, onlineAtStep: 4 },
  { label: "Insight Engine",    icon: Lightbulb,  onlineAtStep: 5 },
  { label: "Agent Graph",       icon: Network,    onlineAtStep: 6 },
  { label: "Report Generator",  icon: FileText,   onlineAtStep: 7 },
  { label: "KPI Monitor",       icon: Activity,   onlineAtStep: 8 },
] as const;

// Agent pipeline nodes
const AGENT_NODES = [
  { label: "Dataset",             icon: Database,  activateAtStep: 0 },
  { label: "Query Planner",       icon: Search,    activateAtStep: 3 },
  { label: "Insight Agent",       icon: Lightbulb, activateAtStep: 5 },
  { label: "Root Cause Agent",    icon: GitBranch, activateAtStep: 6 },
  { label: "Recommendation Agent",icon: Sparkles,  activateAtStep: 7 },
  { label: "Executive Briefing",  icon: FileText,  activateAtStep: 9 },
] as const;

// Platform metrics (demo values)
const PLATFORM_METRICS = [
  { label: "Insights Generated", target: 12482, startAt: 500,  duration: 2400 },
  { label: "Forecasts Produced", target: 3917,  startAt: 700,  duration: 2200 },
  { label: "Reports Created",    target: 5201,  startAt: 900,  duration: 2000 },
  { label: "Queries Executed",   target: 87442, startAt: 350,  duration: 2600 },
] as const;

// Hardcoded particle positions (avoids SSR randomness)
const PARTICLES = [
  { x: 8,  y: 18, size: 1.5, delay: 0,    dur: 12 },
  { x: 22, y: 72, size: 2,   delay: 2.4,  dur: 9  },
  { x: 38, y: 35, size: 1,   delay: 5.1,  dur: 14 },
  { x: 55, y: 85, size: 2,   delay: 1.1,  dur: 11 },
  { x: 64, y: 48, size: 1.5, delay: 3.7,  dur: 10 },
  { x: 78, y: 22, size: 1,   delay: 0.7,  dur: 13 },
  { x: 14, y: 60, size: 2,   delay: 6.2,  dur: 9  },
  { x: 87, y: 76, size: 1.5, delay: 4.0,  dur: 12 },
  { x: 32, y: 52, size: 1,   delay: 1.8,  dur: 15 },
  { x: 50, y: 28, size: 2,   delay: 7.3,  dur: 10 },
  { x: 71, y: 63, size: 1.5, delay: 2.9,  dur: 11 },
  { x: 92, y: 42, size: 1,   delay: 5.5,  dur: 13 },
] as const;

// ─────────────────────────────────────────────────────────────────────────────
// Hook — count-up with cubic ease-out
// ─────────────────────────────────────────────────────────────────────────────

function useCountUp(target: number, durationMs: number, startAtMs: number): number {
  const [current, setCurrent] = useState(0);

  useEffect(() => {
    let startTime: number | null = null;
    let rafId: number;

    const startTimer = setTimeout(() => {
      function tick(now: number) {
        if (startTime === null) startTime = now;
        const elapsed = now - startTime;
        const progress = Math.min(elapsed / durationMs, 1);
        const eased = 1 - Math.pow(1 - progress, 3);
        setCurrent(Math.round(eased * target));
        if (progress < 1) rafId = requestAnimationFrame(tick);
      }
      rafId = requestAnimationFrame(tick);
    }, startAtMs);

    return () => {
      clearTimeout(startTimer);
      cancelAnimationFrame(rafId);
    };
  }, [target, durationMs, startAtMs]);

  return current;
}

// ─────────────────────────────────────────────────────────────────────────────
// Framer Motion variants
// ─────────────────────────────────────────────────────────────────────────────

const pageVariants: Variants = {
  hidden:  { opacity: 0 },
  visible: { opacity: 1 },
};

const colVariants: Variants = {
  hidden:  { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.06, delayChildren: 0.15 } },
};

const panelVariants: Variants = {
  hidden:  { opacity: 0, y: 14 },
  visible: { opacity: 1, y: 0  },
};

const logoVariants: Variants = {
  hidden:  { opacity: 0, scale: 0.82 },
  visible: { opacity: 1, scale: 1    },
};

const textVariants: Variants = {
  hidden:  { opacity: 0, y: 10 },
  visible: { opacity: 1, y: 0  },
};

// ─────────────────────────────────────────────────────────────────────────────
// ParticleField
// ─────────────────────────────────────────────────────────────────────────────

function ParticleField() {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
      {PARTICLES.map((p, i) => (
        <div
          key={i}
          className="absolute rounded-full bg-emerald-400/50 animate-particle-float"
          style={{
            left:             `${p.x}%`,
            top:              `${p.y}%`,
            width:            `${p.size}px`,
            height:           `${p.size}px`,
            animationDelay:   `${p.delay}s`,
            animationDuration:`${p.dur}s`,
          }}
        />
      ))}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Background (grid + drifting glow)
// ─────────────────────────────────────────────────────────────────────────────

function Background() {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
      {/* Grid */}
      <div
        className="absolute inset-0 opacity-[0.04]"
        style={{
          backgroundImage:
            "linear-gradient(rgba(255,255,255,0.8) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.8) 1px, transparent 1px)",
          backgroundSize: "28px 28px",
        }}
      />
      {/* Primary drifting blob */}
      <div
        className="absolute animate-blob-drift"
        style={{
          top: "20%", left: "30%",
          width: "600px", height: "600px",
          background: `radial-gradient(circle, rgba(52,211,153,0.22) 0%, transparent 65%)`,
          borderRadius: "50%",
          transform: "translate(-50%, -50%)",
        }}
      />
      {/* Top-right accent */}
      <div
        className="absolute -top-32 -right-32 h-80 w-80 rounded-full opacity-15"
        style={{ background: "radial-gradient(circle, rgba(52,211,153,0.5) 0%, transparent 65%)" }}
      />
      {/* Bottom-left accent */}
      <div
        className="absolute -bottom-20 -left-20 h-64 w-64 rounded-full opacity-10"
        style={{ background: "radial-gradient(circle, rgba(52,211,153,0.6) 0%, transparent 65%)" }}
      />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Header
// ─────────────────────────────────────────────────────────────────────────────

function Header({ isOnline }: { isOnline: boolean }) {
  return (
    <div className="flex flex-col items-center gap-3 pb-6 border-b border-white/8">
      {/* Logo */}
      <motion.div
        variants={logoVariants}
        transition={{ type: "spring", stiffness: 240, damping: 20, delay: 0.05 }}
        className="relative"
      >
        <span
          className="absolute inset-0 rounded-2xl"
          style={{ boxShadow: `0 0 0 6px ${E_DIM}, 0 0 40px rgba(52,211,153,0.12)` }}
          aria-hidden="true"
        />
        <Image
          src="/logo.png"
          alt="DataPilot AI"
          width={56}
          height={56}
          className="rounded-2xl relative z-10"
          priority
        />
      </motion.div>

      {/* Brand */}
      <motion.div
        variants={textVariants}
        transition={{ duration: 0.4, delay: 0.1 }}
        className="text-center space-y-0.5"
      >
        <h1 className="font-display text-xl font-semibold tracking-tight text-white">
          DataPilot AI
        </h1>
        <p className="text-[11px] text-white/45">
          Agentic Business Intelligence Copilot
        </p>
      </motion.div>

      {/* ONLINE pill */}
      <motion.div
        variants={textVariants}
        transition={{ duration: 0.35, delay: 0.18 }}
        className={cn(
          "flex items-center gap-1.5 rounded-full border px-2.5 py-1 transition-all duration-500",
          isOnline
            ? "border-emerald-500/30 bg-emerald-500/10"
            : "border-white/10 bg-white/5"
        )}
      >
        <span
          className={cn(
            "h-1.5 w-1.5 rounded-full transition-colors duration-500",
            isOnline ? "bg-emerald-400" : "bg-white/30"
          )}
          style={isOnline ? { boxShadow: `0 0 6px ${EMERALD}` } : undefined}
        />
        <span className={cn(
          "text-[10px] font-semibold tracking-wider transition-colors duration-500",
          isOnline ? "text-emerald-400" : "text-white/35"
        )}>
          {isOnline ? "ONLINE" : "STARTING"}
        </span>
      </motion.div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Startup Sequence
// ─────────────────────────────────────────────────────────────────────────────

function StepIcon({ state }: { state: "pending" | "active" | "complete" }) {
  if (state === "complete") {
    return (
      <motion.span
        initial={{ scale: 0.3, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: "spring", stiffness: 420, damping: 16 }}
        className="flex h-5 w-5 shrink-0 items-center justify-center"
      >
        <CheckCircle2 className="h-[17px] w-[17px]" style={{ color: EMERALD }} />
      </motion.span>
    );
  }
  if (state === "active") {
    return (
      <span className="relative flex h-5 w-5 shrink-0 items-center justify-center">
        <span className="absolute h-3.5 w-3.5 rounded-full border border-emerald-400/40 animate-ping" />
        <Circle className="h-3 w-3 relative z-10 text-emerald-400/70" />
      </span>
    );
  }
  return (
    <span className="flex h-5 w-5 shrink-0 items-center justify-center">
      <Circle className="h-3 w-3 text-white/20" />
    </span>
  );
}

function StartupSequence({ completedSteps }: { completedSteps: number }) {
  return (
    <div className="space-y-1.5" role="status" aria-live="polite" aria-label="Startup progress">
      <p className="text-[9.5px] font-semibold text-white/35 uppercase tracking-[0.14em] mb-3">
        Startup Sequence
      </p>
      {STARTUP_STEPS.map((step, i) => {
        const state =
          i < completedSteps ? "complete" :
          i === completedSteps ? "active" : "pending";
        return (
          <div
            key={step.label}
            className={cn(
              "flex items-center gap-2.5 transition-all duration-300",
              state === "complete" ? "opacity-100" :
              state === "active"   ? "opacity-75"  : "opacity-25"
            )}
          >
            <StepIcon state={state} />
            <span
              className={cn(
                "text-[11.5px] leading-tight transition-all duration-300",
                state === "complete" ? "text-white font-medium" : "text-white/70"
              )}
            >
              {step.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// System Status Cards
// ─────────────────────────────────────────────────────────────────────────────

function SystemStatusCard({
  label,
  icon: Icon,
  isOnline,
  delay,
}: {
  label: string;
  icon: React.ElementType;
  isOnline: boolean;
  delay: number;
}) {
  return (
    <motion.div
      whileHover={{ y: -2, transition: { duration: 0.15 } }}
      animate={{
        borderColor:     isOnline ? "rgba(52,211,153,0.30)" : "rgba(255,255,255,0.07)",
        backgroundColor: isOnline ? "rgba(52,211,153,0.06)" : "rgba(255,255,255,0.03)",
        boxShadow:       isOnline
          ? "0 0 12px rgba(52,211,153,0.10), inset 0 1px 0 rgba(255,255,255,0.05)"
          : "none",
      }}
      transition={{ duration: 0.45, delay: isOnline ? delay : 0 }}
      className="rounded-xl border p-3 cursor-default"
    >
      <div className="flex items-center justify-between mb-2">
        <Icon
          className={cn(
            "h-3.5 w-3.5 transition-colors duration-400",
            isOnline ? "text-emerald-400" : "text-white/25"
          )}
        />
        <div className="flex items-center gap-1">
          <span
            className={cn(
              "h-1.5 w-1.5 rounded-full transition-all duration-500",
              isOnline ? "bg-emerald-400 animate-pulse-status" : "bg-white/20"
            )}
            style={isOnline ? { boxShadow: `0 0 5px ${EMERALD}` } : undefined}
          />
          <span
            className={cn(
              "text-[9px] font-bold tracking-wider transition-colors duration-400",
              isOnline ? "text-emerald-400" : "text-white/20"
            )}
          >
            {isOnline ? "ONLINE" : "OFFLINE"}
          </span>
        </div>
      </div>
      <p
        className={cn(
          "text-[11px] font-medium leading-tight transition-colors duration-400",
          isOnline ? "text-white/85" : "text-white/25"
        )}
      >
        {label}
      </p>
    </motion.div>
  );
}

function SystemStatus({ completedSteps }: { completedSteps: number }) {
  return (
    <div>
      <p className="text-[9.5px] font-semibold text-white/35 uppercase tracking-[0.14em] mb-3">
        System Status
      </p>
      <div className="grid grid-cols-2 gap-2">
        {SYSTEM_SERVICES.map(({ label, icon, onlineAtStep }, i) => (
          <SystemStatusCard
            key={label}
            label={label}
            icon={icon}
            isOnline={completedSteps >= onlineAtStep}
            delay={i * 0.04}
          />
        ))}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Agent Network Visualization
// ─────────────────────────────────────────────────────────────────────────────

function AgentNetwork({ completedSteps }: { completedSteps: number }) {
  return (
    <div>
      <p className="text-[9.5px] font-semibold text-white/35 uppercase tracking-[0.14em] mb-3">
        Agent Network
      </p>
      <div className="flex flex-col items-center">
        {AGENT_NODES.map(({ label, icon: Icon, activateAtStep }, i) => {
          const active = completedSteps >= activateAtStep;
          const isLast = i === AGENT_NODES.length - 1;

          return (
            <div key={label} className="flex flex-col items-center w-full">
              {/* Node pill */}
              <motion.div
                animate={{
                  borderColor:     active ? "rgba(52,211,153,0.35)" : "rgba(255,255,255,0.07)",
                  backgroundColor: active ? "rgba(52,211,153,0.08)" : "rgba(255,255,255,0.02)",
                  boxShadow:       active
                    ? `0 0 10px rgba(52,211,153,0.12), inset 0 1px 0 rgba(255,255,255,0.05)`
                    : "none",
                }}
                transition={{ duration: 0.4 }}
                className="flex items-center gap-2 rounded-lg border w-full px-2.5 py-2 cursor-default"
              >
                <span
                  className={cn(
                    "flex h-5 w-5 shrink-0 items-center justify-center rounded-md transition-colors duration-400",
                    active ? "bg-emerald-500/20" : "bg-white/5"
                  )}
                >
                  <Icon
                    className={cn(
                      "h-3 w-3 transition-colors duration-400",
                      active ? "text-emerald-400" : "text-white/20"
                    )}
                  />
                </span>
                <span
                  className={cn(
                    "text-[10.5px] font-medium transition-colors duration-400 truncate",
                    active ? "text-white/85" : "text-white/22"
                  )}
                >
                  {label}
                </span>
                {active && (
                  <motion.span
                    initial={{ opacity: 0, scale: 0.5 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ type: "spring", stiffness: 400, damping: 20 }}
                    className="ml-auto shrink-0 h-1 w-1 rounded-full bg-emerald-400"
                    style={{ boxShadow: `0 0 4px ${EMERALD}` }}
                  />
                )}
              </motion.div>

              {/* Connector */}
              {!isLast && (
                <div className="relative w-px h-6 mx-auto my-0.5 bg-white/8">
                  {active && (
                    <div
                      className="absolute w-full rounded-full bg-emerald-400"
                      style={{
                        height: "35%",
                        animation: `flow-dot-v 1.4s linear infinite`,
                        animationDelay: `${i * 0.22}s`,
                        top: 0,
                      }}
                    />
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Metric Counter
// ─────────────────────────────────────────────────────────────────────────────

function MetricCounter({
  label,
  target,
  startAt,
  duration,
}: {
  label: string;
  target: number;
  startAt: number;
  duration: number;
}) {
  const count = useCountUp(target, duration, startAt);

  return (
    <div className="text-center space-y-1">
      <p
        className="text-xl font-bold text-white tabular-nums"
        style={{ fontVariantNumeric: "tabular-nums" }}
      >
        {count.toLocaleString("en-US")}
      </p>
      <p className="text-[9.5px] text-white/38 font-medium">{label}</p>
    </div>
  );
}

function MetricsRow() {
  return (
    <div
      className="rounded-xl border border-white/8 bg-white/[0.025] px-4 py-4"
      aria-hidden="true"
    >
      <p className="text-[9.5px] font-semibold text-white/35 uppercase tracking-[0.14em] text-center mb-4">
        Platform Activity
      </p>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {PLATFORM_METRICS.map((m) => (
          <MetricCounter key={m.label} {...m} />
        ))}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Progress Bar
// ─────────────────────────────────────────────────────────────────────────────

function ProgressBar({ totalMs }: { totalMs: number }) {
  return (
    <div className="h-px w-full bg-white/8 rounded-full overflow-hidden" aria-hidden="true">
      <div
        className="h-full bg-gradient-to-r from-emerald-600 to-emerald-400 rounded-full"
        style={{
          width: "100%",
          transform: "scaleX(0)",
          transformOrigin: "left",
          transition: `transform ${totalMs / 1000}s linear`,
        }}
        ref={(el) => {
          if (el) requestAnimationFrame(() => { el.style.transform = "scaleX(1)"; });
        }}
      />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Workspace Ready Screen
// ─────────────────────────────────────────────────────────────────────────────

function WorkspaceReadyScreen() {
  return (
    <div className="flex flex-col items-center gap-5 text-center">
      <motion.div
        initial={{ scale: 0.3, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: "spring", stiffness: 260, damping: 16 }}
        className="relative flex items-center justify-center"
      >
        <span
          className="absolute h-20 w-20 rounded-full"
          style={{ background: "radial-gradient(circle, rgba(52,211,153,0.2) 0%, transparent 70%)" }}
          aria-hidden="true"
        />
        <CheckCircle
          className="relative z-10 h-14 w-14"
          style={{ color: EMERALD }}
        />
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.15 }}
        className="space-y-1.5"
      >
        <h2 className="font-display text-2xl font-semibold text-white tracking-tight">
          Workspace Ready
        </h2>
        <p className="text-[11.5px] text-white/40">
          Redirecting to your workspace…
        </p>
      </motion.div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main component
// ─────────────────────────────────────────────────────────────────────────────

export interface WorkspaceLoaderProps {
  destination: string;
}

export function WorkspaceLoader({ destination }: WorkspaceLoaderProps) {
  const router = useRouter();
  const [completedSteps, setCompletedSteps] = useState(0);
  const [isReady, setIsReady]     = useState(false);
  const [isExiting, setIsExiting] = useState(false);
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  const pushTimer = useCallback((cb: () => void, ms: number) => {
    const t = setTimeout(cb, ms);
    timersRef.current.push(t);
  }, []);

  useEffect(() => {
    // Schedule each step completion
    STARTUP_STEPS.forEach((step, i) => {
      pushTimer(() => setCompletedSteps(i + 1), step.completeAt);
    });

    // Transition to "Workspace Ready"
    pushTimer(() => setIsReady(true), READY_AT);

    // Start exit overlay
    pushTimer(() => setIsExiting(true), EXITING_AT);

    return () => {
      timersRef.current.forEach(clearTimeout);
      timersRef.current = [];
    };
  }, [pushTimer]);

  return (
    <motion.div
      initial="hidden"
      animate="visible"
      variants={pageVariants}
      transition={{ duration: 0.4 }}
      className="relative min-h-screen w-full flex flex-col overflow-hidden"
      style={{ backgroundColor: BG }}
      aria-label="DataPilot AI workspace loading"
      role="status"
    >
      <Background />
      <ParticleField />

      {/* ── Main content — fades/blurs out when ready ── */}
      <motion.div
        animate={isReady ? { opacity: 0, scale: 0.98, filter: "blur(4px)" } : { opacity: 1, scale: 1, filter: "blur(0px)" }}
        transition={{ duration: 0.25 }}
        className="relative flex flex-col flex-1 px-6 py-8 md:px-10 md:py-10 max-w-5xl mx-auto w-full"
      >
        {/* Header */}
        <motion.div initial="hidden" animate="visible" variants={colVariants}>
          <Header isOnline={completedSteps >= 3} />
        </motion.div>

        {/* Three-column panel */}
        <motion.div
          initial="hidden"
          animate="visible"
          variants={colVariants}
          className="grid grid-cols-1 md:grid-cols-3 gap-5 mt-6 flex-1"
        >
          <motion.div variants={panelVariants} transition={{ duration: 0.35 }}>
            <StartupSequence completedSteps={completedSteps} />
          </motion.div>

          <motion.div variants={panelVariants} transition={{ duration: 0.35 }}>
            <SystemStatus completedSteps={completedSteps} />
          </motion.div>

          <motion.div
            variants={panelVariants}
            transition={{ duration: 0.35 }}
            className="hidden md:block"
          >
            <AgentNetwork completedSteps={completedSteps} />
          </motion.div>
        </motion.div>

        {/* Metrics row */}
        <motion.div
          initial="hidden"
          animate="visible"
          variants={panelVariants}
          transition={{ duration: 0.35, delay: 0.25 }}
          className="mt-5"
        >
          <MetricsRow />
        </motion.div>

        {/* Progress bar */}
        <div className="mt-4">
          <ProgressBar totalMs={READY_AT} />
        </div>
      </motion.div>

      {/* ── "Workspace Ready" overlay ── */}
      <AnimatePresence>
        {isReady && (
          <motion.div
            key="ready"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.3, delay: 0.2 }}
            className="absolute inset-0 flex items-center justify-center"
            style={{ backgroundColor: BG }}
          >
            <WorkspaceReadyScreen />
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Final fade-to-background exit overlay ── */}
      <AnimatePresence>
        {isExiting && (
          <motion.div
            key="exit"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.3 }}
            className="absolute inset-0 z-50"
            style={{ backgroundColor: BG }}
            onAnimationComplete={() => router.replace(destination)}
          />
        )}
      </AnimatePresence>
    </motion.div>
  );
}
