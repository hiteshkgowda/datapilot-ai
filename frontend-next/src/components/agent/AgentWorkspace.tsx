"use client";

import { useCallback, useEffect, useState } from "react";
import { Bot } from "lucide-react";
import { cn } from "@/lib/utils";
import { AgentGoalInput } from "./AgentGoalInput";
import { AgentSessionList } from "./AgentSessionList";
import { AgentThread } from "./AgentThread";
import { AgentTimeline } from "./AgentTimeline";
import { useAgentExplain, useAgentResume, useAgentRun } from "@/hooks/use-agent";
import {
  loadSessions,
  saveSessions,
  uid,
  type AgentContext,
  type AgentConversationTurn,
  type StoredSession,
} from "./types";
import type { AgentStatus } from "@/lib/api/types";
import type { ToolResult } from "@/lib/api/types";

// ── Status indicator config ───────────────────────────────────────────────────

const STATUS_DOT: Record<AgentStatus, string> = {
  running: "status-dot-pending",
  suspended: "status-dot-pending",
  done: "status-dot-online",
  failed: "status-dot-offline",
};

const STATUS_LABEL: Record<AgentStatus, string> = {
  running: "Running",
  suspended: "Awaiting approval",
  done: "Complete",
  failed: "Failed",
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function initialSession(): StoredSession {
  return {
    id: uid(),
    goal: "",
    timestamp: new Date().toISOString(),
    status: "running",
    turns: [],
    completedSteps: [],
    pendingApproval: null,
    finalAnswer: null,
    error: null,
  };
}

// ── Component ─────────────────────────────────────────────────────────────────

export function AgentWorkspace() {
  // Initialize empty — localStorage is not available during SSR.
  // useEffect populates state after mount to avoid hydration mismatch.
  const [sessions, setSessions] = useState<StoredSession[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [prefill, setPrefill] = useState<string | undefined>();

  useEffect(() => {
    const loaded = loadSessions();
    setSessions(loaded);
    if (loaded.length > 0) setActiveId(loaded[0].id);
  }, []);

  const runMutation = useAgentRun();
  const resumeMutation = useAgentResume();
  const explainMutation = useAgentExplain();

  const activeSession = sessions.find((s) => s.id === activeId) ?? null;

  // ── Session helpers ─────────────────────────────────────────────────────────

  const updateSession = useCallback(
    (id: string, patch: Partial<StoredSession>) => {
      setSessions((prev) => {
        const next = prev.map((s) => (s.id === id ? { ...s, ...patch } : s));
        saveSessions(next);
        return next;
      });
    },
    []
  );

  const pushTurn = useCallback(
    (id: string, turn: AgentConversationTurn) => {
      setSessions((prev) => {
        const next = prev.map((s) =>
          s.id === id ? { ...s, turns: [...s.turns, turn] } : s
        );
        saveSessions(next);
        return next;
      });
    },
    []
  );

  const createSession = useCallback(() => {
    const s = initialSession();
    setSessions((prev) => {
      const next = [s, ...prev];
      saveSessions(next);
      return next;
    });
    setActiveId(s.id);
    return s;
  }, []);

  // ── Run ─────────────────────────────────────────────────────────────────────

  const handleRun = useCallback(
    async (goal: string, ctx: Partial<AgentContext>) => {
      const session = createSession();
      updateSession(session.id, { goal, status: "running" });

      pushTurn(session.id, {
        role: "user",
        id: uid(),
        timestamp: new Date().toISOString(),
        content: goal,
      });

      try {
        const result = await runMutation.mutateAsync({
          question: goal,
          dataset_id: ctx.datasetId,
          connection_id: ctx.connectionId,
        });

        if (result.status === "suspended" && result.pending_approval) {
          updateSession(session.id, {
            status: "suspended",
            completedSteps: result.completed_steps,
            pendingApproval: result.pending_approval,
          });
          pushTurn(session.id, {
            role: "approval",
            id: uid(),
            timestamp: new Date().toISOString(),
            approval: result.pending_approval,
            sessionId: result.session_id,
          });
        } else {
          updateSession(session.id, {
            status: result.status,
            completedSteps: result.completed_steps,
            finalAnswer: result.final_answer,
            pendingApproval: null,
            error: result.error,
          });
          pushTurn(session.id, {
            role: "agent",
            id: uid(),
            timestamp: new Date().toISOString(),
            answer: result.final_answer ?? "",
            steps: result.completed_steps,
            status: result.status,
            sessionId: result.session_id,
            error: result.error,
          });
        }
      } catch {
        updateSession(session.id, { status: "failed" });
        pushTurn(session.id, {
          role: "error",
          id: uid(),
          timestamp: new Date().toISOString(),
          message: "Agent run failed. Check the console for details.",
        });
      }
    },
    [createSession, updateSession, pushTurn, runMutation]
  );

  // ── Approve / Reject ────────────────────────────────────────────────────────

  const handleApprove = useCallback(
    async (sessionId: string) => {
      try {
        const result = await resumeMutation.mutateAsync({
          sessionId,
          request: { approved: true },
        });

        if (!activeId) return;

        if (result.status === "suspended" && result.pending_approval) {
          updateSession(activeId, {
            status: "suspended",
            completedSteps: result.completed_steps,
            pendingApproval: result.pending_approval,
          });
          pushTurn(activeId, {
            role: "approval",
            id: uid(),
            timestamp: new Date().toISOString(),
            approval: result.pending_approval,
            sessionId: result.session_id,
          });
        } else {
          updateSession(activeId, {
            status: result.status,
            completedSteps: result.completed_steps,
            finalAnswer: result.final_answer,
            pendingApproval: null,
            error: result.error,
          });
          pushTurn(activeId, {
            role: "agent",
            id: uid(),
            timestamp: new Date().toISOString(),
            answer: result.final_answer ?? "",
            steps: result.completed_steps,
            status: result.status,
            sessionId: result.session_id,
            error: result.error,
          });
        }
      } catch {
        if (!activeId) return;
        updateSession(activeId, { status: "failed" });
        pushTurn(activeId, {
          role: "error",
          id: uid(),
          timestamp: new Date().toISOString(),
          message: "Resume failed after approval.",
        });
      }
    },
    [activeId, resumeMutation, updateSession, pushTurn]
  );

  const handleReject = useCallback(
    async (sessionId: string) => {
      try {
        const result = await resumeMutation.mutateAsync({
          sessionId,
          request: { approved: false },
        });

        if (!activeId) return;

        updateSession(activeId, {
          status: result.status,
          completedSteps: result.completed_steps,
          finalAnswer: result.final_answer,
          pendingApproval: null,
          error: result.error,
        });
        pushTurn(activeId, {
          role: "agent",
          id: uid(),
          timestamp: new Date().toISOString(),
          answer: result.final_answer ?? "Operation rejected.",
          steps: result.completed_steps,
          status: result.status,
          sessionId: result.session_id,
          error: result.error,
        });
      } catch {
        // silent — approval card remains
      }
    },
    [activeId, resumeMutation, updateSession, pushTurn]
  );

  // ── Explain ─────────────────────────────────────────────────────────────────

  const handleExplain = useCallback(
    async (goal: string, ctx: Partial<AgentContext>) => {
      const session = createSession();
      updateSession(session.id, { goal, status: "done" });

      pushTurn(session.id, {
        role: "user",
        id: uid(),
        timestamp: new Date().toISOString(),
        content: `(Explain) ${goal}`,
      });

      try {
        const result = await explainMutation.mutateAsync({
          question: goal,
          dataset_id: ctx.datasetId,
          connection_id: ctx.connectionId,
        });
        pushTurn(session.id, {
          role: "explain",
          id: uid(),
          timestamp: new Date().toISOString(),
          goal,
          explain: result,
        });
      } catch {
        pushTurn(session.id, {
          role: "error",
          id: uid(),
          timestamp: new Date().toISOString(),
          message: "Could not retrieve agent plan.",
        });
      }
    },
    [createSession, updateSession, pushTurn, explainMutation]
  );

  // ── Derived ─────────────────────────────────────────────────────────────────

  const timelineSteps: ToolResult[] = activeSession?.completedSteps ?? [];

  const isPending =
    runMutation.isPending ||
    resumeMutation.isPending ||
    explainMutation.isPending;

  const handleExample = useCallback((q: string) => {
    setPrefill(q);
  }, []);

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="flex h-full min-h-0">
      {/* ── Left: session list ─────────────────────────────────────── */}
      <aside className="w-64 shrink-0 border-r border-border/60 overflow-hidden flex flex-col bg-sidebar">
        <AgentSessionList
          sessions={sessions}
          activeId={activeId}
          onSelect={setActiveId}
          onNew={() => {
            const s = createSession();
            setActiveId(s.id);
          }}
        />
      </aside>

      {/* ── Center: thread + input ─────────────────────────────────── */}
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Title bar */}
        <div className="flex h-11 items-center justify-between px-4 border-b border-border/60 shrink-0 bg-background/95 backdrop-blur-sm">
          <div className="flex items-center gap-2.5 min-w-0">
            <div
              className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-gradient-primary elevation-glow-sm"
              aria-hidden="true"
            >
              <Bot className="h-3 w-3 text-white" />
            </div>
            <span className="text-sm font-semibold text-foreground truncate">
              {activeSession?.goal
                ? activeSession.goal.slice(0, 60)
                : "New session"}
            </span>
          </div>

          {activeSession && (
            <div className="flex items-center gap-1.5 shrink-0">
              <span
                className={cn(STATUS_DOT[activeSession.status])}
                aria-hidden="true"
              />
              <span className="text-xs text-muted-foreground/60">
                {STATUS_LABEL[activeSession.status]}
              </span>
            </div>
          )}
        </div>

        {/* Thread — self-contained with scroll */}
        <AgentThread
          turns={activeSession?.turns ?? []}
          isPending={isPending}
          isResuming={resumeMutation.isPending}
          onApprove={handleApprove}
          onReject={handleReject}
          onExample={handleExample}
        />

        {/* Input */}
        <AgentGoalInput
          onRun={handleRun}
          onExplain={handleExplain}
          isPending={isPending}
          prefill={prefill}
          onPrefillConsumed={() => setPrefill(undefined)}
        />
      </main>

      {/* ── Right: execution timeline ──────────────────────────────── */}
      <aside className="w-72 shrink-0 border-l border-border/60 overflow-hidden flex flex-col bg-sidebar">
        <AgentTimeline steps={timelineSteps} isPending={isPending} />
      </aside>
    </div>
  );
}
