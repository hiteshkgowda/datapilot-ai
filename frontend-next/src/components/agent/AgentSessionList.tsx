"use client";

import { motion } from "framer-motion";
import { Bot, Plus } from "lucide-react";
import { cn } from "@/lib/utils";
import type { AgentStatus } from "@/lib/api/types";
import type { StoredSession } from "./types";

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60) return "just now";
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

const STATUS_DOT: Record<AgentStatus, string> = {
  done: "status-dot-online",
  running: "status-dot-pending",
  suspended: "status-dot-pending",
  failed: "status-dot-offline",
};

const STATUS_LABEL: Record<AgentStatus, string> = {
  done: "Done",
  running: "Running",
  suspended: "Awaiting",
  failed: "Failed",
};

interface SessionRowProps {
  session: StoredSession;
  isActive: boolean;
  onClick: () => void;
}

function SessionRow({ session, isActive, onClick }: SessionRowProps) {
  return (
    <motion.button
      initial={{ opacity: 0, x: -6 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.18, ease: "easeOut" }}
      onClick={onClick}
      className={cn(
        "relative w-full text-left rounded-lg px-3 py-2.5 transition-all duration-150 group overflow-hidden",
        isActive ? "bg-sidebar-active" : "hover:bg-muted/30"
      )}
    >
      {/* Active left accent */}
      {isActive && (
        <span className="absolute left-0 top-1/2 -translate-y-1/2 h-8 w-0.5 rounded-r-full bg-primary" />
      )}

      <div className="flex items-start gap-2.5 pl-1">
        {/* Status dot */}
        <span
          className={cn("mt-1.5 shrink-0", STATUS_DOT[session.status])}
          aria-label={STATUS_LABEL[session.status]}
        />

        <div className="flex-1 min-w-0">
          <p
            className={cn(
              "text-xs font-medium line-clamp-2 leading-snug",
              isActive
                ? "text-foreground"
                : "text-muted-foreground group-hover:text-foreground"
            )}
          >
            {session.goal || "New session"}
          </p>
          <p className="mt-1 text-[10px] text-muted-foreground/50 tabular-nums">
            {relativeTime(session.timestamp)}
            {session.completedSteps.length > 0 && (
              <span className="ml-2">
                {session.completedSteps.length} step
                {session.completedSteps.length !== 1 ? "s" : ""}
              </span>
            )}
          </p>
        </div>
      </div>
    </motion.button>
  );
}

interface AgentSessionListProps {
  sessions: StoredSession[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
}

export function AgentSessionList({
  sessions,
  activeId,
  onSelect,
  onNew,
}: AgentSessionListProps) {
  const active = sessions.filter(
    (s) => s.status === "running" || s.status === "suspended"
  );
  const history = sessions.filter(
    (s) => s.status !== "running" && s.status !== "suspended"
  );

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-4 py-3 border-b border-border/60 shrink-0 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="flex h-5 w-5 items-center justify-center rounded-md bg-primary/10">
              <Bot className="h-3 w-3 text-primary" aria-hidden="true" />
            </div>
            <span className="text-sm font-semibold text-foreground">Sessions</span>
          </div>
          {sessions.length > 0 && (
            <span className="text-[10px] text-muted-foreground/40 tabular-nums">
              {sessions.length}
            </span>
          )}
        </div>

        <button
          onClick={onNew}
          className={cn(
            "w-full flex items-center justify-center gap-1.5 rounded-lg border border-dashed border-border/50",
            "px-3 py-1.5 text-xs text-muted-foreground/60",
            "hover:text-foreground hover:border-primary/40 hover:bg-primary/5",
            "transition-all duration-150",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          )}
        >
          <Plus className="h-3 w-3" aria-hidden="true" />
          New session
        </button>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto py-2 min-h-0">
        {sessions.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 px-4 gap-3 text-center">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-muted/20">
              <Bot className="h-5 w-5 text-muted-foreground/20" aria-hidden="true" />
            </div>
            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground">No sessions yet</p>
              <p className="text-[11px] text-muted-foreground/50 leading-relaxed">
                Describe a goal to get started
              </p>
            </div>
          </div>
        ) : (
          <div className="space-y-0.5 px-2">
            {active.length > 0 && (
              <div className="mb-2">
                <p className="px-2 pb-1 pt-0.5 text-[10px] font-medium text-muted-foreground/50 uppercase tracking-wide">
                  Active
                </p>
                {active.map((s) => (
                  <SessionRow
                    key={s.id}
                    session={s}
                    isActive={s.id === activeId}
                    onClick={() => onSelect(s.id)}
                  />
                ))}
              </div>
            )}

            {history.length > 0 && (
              <div>
                {active.length > 0 && (
                  <p className="px-2 pb-1 pt-1 text-[10px] font-medium text-muted-foreground/50 uppercase tracking-wide">
                    History
                  </p>
                )}
                {history.map((s) => (
                  <SessionRow
                    key={s.id}
                    session={s}
                    isActive={s.id === activeId}
                    onClick={() => onSelect(s.id)}
                  />
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
