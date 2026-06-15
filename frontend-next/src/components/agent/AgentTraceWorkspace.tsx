"use client";

import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import {
  AlertCircle,
  Bot,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  GitBranch,
  Loader2,
  ShieldAlert,
  XCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { getAgentSession } from "@/lib/api/agent";
import {
  loadSessions,
  SESSION_STORAGE_KEY,
  type StoredSession,
} from "./types";

function getBackendSessionId(session: StoredSession): string | null {
  for (const turn of session.turns) {
    if (
      (turn.role === "agent" || turn.role === "approval") &&
      "sessionId" in turn &&
      typeof turn.sessionId === "string" &&
      turn.sessionId.length === 32
    ) {
      return turn.sessionId;
    }
  }
  return null;
}
import type { AgentSessionInfo, AgentStatus, PlannedToolCall, ToolResult } from "@/lib/api/types";
import { useState, useEffect } from "react";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const TOOL_LABEL: Record<string, string> = {
  query: "SQL Query",
  chart: "Chart Generation",
  forecast: "Forecast",
  insight: "Insights",
  rca: "Root Cause Analysis",
  recommendation: "Recommendations",
  report: "PDF Report",
  crud_preview: "CRUD Preview",
  crud_execute: "CRUD Execute",
};

const STATUS_CONFIG: Record<AgentStatus, { label: string; color: string; icon: React.ElementType }> = {
  running:   { label: "Running",           color: "text-amber-500",  icon: Loader2 },
  suspended: { label: "Awaiting Approval", color: "text-blue-500",   icon: ShieldAlert },
  done:      { label: "Complete",          color: "text-emerald-500", icon: CheckCircle2 },
  failed:    { label: "Failed",            color: "text-red-500",    icon: XCircle },
};

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StatusBadge({ status }: { status: AgentStatus }) {
  const { label, color, icon: Icon } = STATUS_CONFIG[status] ?? STATUS_CONFIG.running;
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-xs font-medium", color)}>
      <Icon className="h-3.5 w-3.5" aria-hidden />
      {label}
    </span>
  );
}

function DurationBadge({ ms }: { ms: number }) {
  const display = ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`;
  return (
    <span className="inline-flex items-center gap-1 text-[10px] text-muted-foreground font-mono">
      <Clock className="h-3 w-3" />
      {display}
    </span>
  );
}

type StepState = "done" | "error" | "active" | "pending";

function stepState(
  index: number,
  currentStep: number,
  status: AgentStatus,
  result: ToolResult | undefined,
): StepState {
  if (result) return result.error ? "error" : "done";
  if (index === currentStep && (status === "running" || status === "suspended")) return "active";
  return "pending";
}

const STEP_STATE_STYLES: Record<StepState, { ring: string; dot: string; label: string }> = {
  done:    { ring: "border-emerald-500/40 bg-emerald-500/5",  dot: "bg-emerald-500",  label: "Done" },
  error:   { ring: "border-red-500/40 bg-red-500/5",          dot: "bg-red-500",      label: "Error" },
  active:  { ring: "border-amber-500/40 bg-amber-500/5",      dot: "bg-amber-500 animate-pulse", label: "Running" },
  pending: { ring: "border-border bg-card",                   dot: "bg-muted",        label: "Pending" },
};

function OutputViewer({ output }: { output: Record<string, unknown> }) {
  const [open, setOpen] = useState(false);
  const answer = typeof output.answer === "string" ? output.answer : null;
  const hasMore = Object.keys(output).length > 1 || (!answer && Object.keys(output).length > 0);

  return (
    <div className="mt-2 space-y-1.5">
      {answer && (
        <p className="text-xs text-foreground/80 leading-relaxed line-clamp-3">{answer}</p>
      )}
      {hasMore && (
        <>
          <button
            onClick={() => setOpen((v) => !v)}
            className="inline-flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground transition-colors"
          >
            {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
            {open ? "Hide raw output" : "Show raw output"}
          </button>
          <AnimatePresence>
            {open && (
              <motion.pre
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.18 }}
                className="overflow-hidden text-[10px] font-mono bg-muted/40 rounded p-2 whitespace-pre-wrap break-all max-h-48 overflow-y-auto"
              >
                {JSON.stringify(output, null, 2)}
              </motion.pre>
            )}
          </AnimatePresence>
        </>
      )}
    </div>
  );
}

function StepCard({
  index,
  plan,
  result,
  currentStep,
  status,
}: {
  index: number;
  plan: PlannedToolCall;
  result: ToolResult | undefined;
  currentStep: number;
  status: AgentStatus;
}) {
  const state = stepState(index, currentStep, status, result);
  const styles = STEP_STATE_STYLES[state];
  const toolLabel = TOOL_LABEL[plan.tool_name] ?? plan.tool_name;

  return (
    <motion.div
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.05 }}
      className={cn("relative flex gap-3 rounded-lg border p-3", styles.ring)}
    >
      {/* Step number + connector line */}
      <div className="flex flex-col items-center gap-1 shrink-0 pt-0.5">
        <div className={cn("h-5 w-5 rounded-full flex items-center justify-center shrink-0", styles.dot)}>
          {state === "active" ? (
            <Loader2 className="h-2.5 w-2.5 text-white animate-spin" />
          ) : state === "done" ? (
            <CheckCircle2 className="h-2.5 w-2.5 text-white" />
          ) : state === "error" ? (
            <XCircle className="h-2.5 w-2.5 text-white" />
          ) : (
            <span className="text-[9px] font-bold text-muted-foreground">{index + 1}</span>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs font-semibold text-foreground">{plan.step_label}</span>
          <span className="text-[10px] text-muted-foreground font-mono bg-muted/60 px-1.5 py-0.5 rounded">
            {toolLabel}
          </span>
          {plan.requires_approval && (
            <span className="inline-flex items-center gap-0.5 text-[10px] text-blue-500 bg-blue-500/10 px-1.5 py-0.5 rounded">
              <ShieldAlert className="h-2.5 w-2.5" />
              approval
            </span>
          )}
          {result && <DurationBadge ms={result.duration_ms} />}
          <span className={cn(
            "ml-auto text-[10px] font-medium",
            state === "done" ? "text-emerald-500" :
            state === "error" ? "text-red-500" :
            state === "active" ? "text-amber-500" :
            "text-muted-foreground"
          )}>
            {styles.label}
          </span>
        </div>

        {/* Error message */}
        {result?.error && (
          <div className="mt-1.5 flex items-start gap-1.5 text-xs text-red-500">
            <AlertCircle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
            <span>{result.error}</span>
          </div>
        )}

        {/* Output */}
        {result && !result.error && Object.keys(result.output).length > 0 && (
          <OutputViewer output={result.output} />
        )}
      </div>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Session detail view
// ---------------------------------------------------------------------------

function TraceDetail({ sessionId }: { sessionId: string }) {
  const { data, isLoading, isError, error } = useQuery<AgentSessionInfo>({
    queryKey: ["agent-session", sessionId],
    queryFn: () => getAgentSession(sessionId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "running" || status === "suspended" ? 2000 : false;
    },
  });

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-3 text-muted-foreground">
        <Loader2 className="h-8 w-8 animate-spin" />
        <p className="text-sm">Loading session…</p>
      </div>
    );
  }

  if (isError || !data) {
    const msg = (error as Error)?.message ?? "Session not found";
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-3">
        <XCircle className="h-10 w-10 text-red-400" />
        <p className="text-sm text-muted-foreground">{msg}</p>
      </div>
    );
  }

  const completedByIndex: Record<number, ToolResult> = {};
  data.completed_results.forEach((r, i) => {
    completedByIndex[i] = r;
  });

  const totalMs = data.completed_results.reduce((s, r) => s + r.duration_ms, 0);

  return (
    <div className="max-w-2xl mx-auto space-y-5 py-6">
      {/* Session header */}
      <div className="rounded-xl border bg-card p-4 space-y-2">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2">
            <Bot className="h-4 w-4 text-primary shrink-0" />
            <p className="text-sm font-semibold text-foreground">{data.user_goal}</p>
          </div>
          <StatusBadge status={data.status} />
        </div>
        <div className="flex items-center gap-3 flex-wrap text-[11px] text-muted-foreground">
          <span>{data.completed_results.length} / {data.total_steps} steps complete</span>
          {totalMs > 0 && <span>Total time: {(totalMs / 1000).toFixed(1)}s</span>}
          <span className="font-mono text-[10px] opacity-60">{sessionId.slice(0, 16)}…</span>
        </div>
      </div>

      {/* Final answer */}
      {data.final_answer && (
        <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-emerald-600 mb-1.5">
            Final Answer
          </p>
          <p className="text-sm text-foreground/90 leading-relaxed whitespace-pre-wrap">
            {data.final_answer}
          </p>
        </div>
      )}

      {/* Error */}
      {data.error && data.status === "failed" && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-4 flex gap-2">
          <AlertCircle className="h-4 w-4 text-red-500 shrink-0 mt-0.5" />
          <p className="text-sm text-red-600">{data.error}</p>
        </div>
      )}

      {/* Steps */}
      {data.plan.length > 0 ? (
        <div className="space-y-2">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground px-1">
            Execution Plan · {data.plan.length} steps
          </p>
          {data.plan.map((step, i) => (
            <StepCard
              key={i}
              index={i}
              plan={step}
              result={completedByIndex[i]}
              currentStep={data.current_step}
              status={data.status}
            />
          ))}
        </div>
      ) : (
        <div className="rounded-xl border bg-card p-6 text-center text-sm text-muted-foreground">
          No execution plan recorded for this session.
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Session selector (when no session_id in URL)
// ---------------------------------------------------------------------------

function SessionPicker({ onSelect }: { onSelect: (id: string) => void }) {
  const [sessions, setSessions] = useState<StoredSession[]>([]);

  useEffect(() => {
    setSessions(loadSessions());

    function onStorage(e: StorageEvent) {
      if (e.key === SESSION_STORAGE_KEY) setSessions(loadSessions());
    }
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  if (sessions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-32 gap-4 text-muted-foreground">
        <GitBranch className="h-12 w-12 opacity-30" />
        <p className="text-sm">No agent sessions yet.</p>
        <p className="text-xs opacity-70">Run a query from the Agent page, then come back to inspect the trace.</p>
      </div>
    );
  }

  const STATUS_DOT: Record<AgentStatus, string> = {
    running: "bg-amber-400",
    suspended: "bg-blue-400",
    done: "bg-emerald-400",
    failed: "bg-red-400",
  };

  return (
    <div className="max-w-2xl mx-auto py-6 space-y-3">
      <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground px-1">
        Recent Sessions
      </p>
      {sessions.map((s) => {
        const backendId = getBackendSessionId(s);
        return (
        <button
          key={s.id}
          onClick={() => backendId && onSelect(backendId)}
          disabled={!backendId}
          className="w-full rounded-xl border bg-card hover:border-primary/40 hover:bg-primary/5 transition-colors p-4 text-left group disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <div className="flex items-start gap-3">
            <div className={cn("h-2 w-2 rounded-full mt-1.5 shrink-0", STATUS_DOT[s.status] ?? "bg-muted")} />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-foreground truncate group-hover:text-primary transition-colors">
                {s.goal || "Untitled session"}
              </p>
              <div className="flex items-center gap-3 mt-0.5 text-[11px] text-muted-foreground">
                <span>{new Date(s.timestamp).toLocaleString()}</span>
                <span>{s.completedSteps.length} steps completed</span>
                <span className={cn(
                  "font-medium",
                  s.status === "done" ? "text-emerald-500" :
                  s.status === "failed" ? "text-red-500" :
                  s.status === "running" ? "text-amber-500" : "text-blue-500"
                )}>
                  {STATUS_CONFIG[s.status]?.label ?? s.status}
                </span>
              </div>
            </div>
            <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0 mt-1 group-hover:text-primary transition-colors" />
          </div>
        </button>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main workspace
// ---------------------------------------------------------------------------

export function AgentTraceWorkspace() {
  const searchParams = useSearchParams();
  const urlSessionId = searchParams.get("session_id");
  const [selectedId, setSelectedId] = useState<string | null>(urlSessionId);

  useEffect(() => {
    setSelectedId(urlSessionId);
  }, [urlSessionId]);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="shrink-0 border-b px-6 py-4 flex items-center gap-3">
        <GitBranch className="h-5 w-5 text-primary" />
        <div>
          <h1 className="text-base font-semibold leading-none">Agent Trace Viewer</h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Inspect execution plans, step timing, and outputs for any agent session
          </p>
        </div>
        {selectedId && (
          <button
            onClick={() => setSelectedId(null)}
            className="ml-auto text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            ← All sessions
          </button>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-6">
        <AnimatePresence mode="wait">
          {selectedId ? (
            <motion.div
              key={selectedId}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.18 }}
            >
              <TraceDetail sessionId={selectedId} />
            </motion.div>
          ) : (
            <motion.div
              key="picker"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.18 }}
            >
              <SessionPicker onSelect={setSelectedId} />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
