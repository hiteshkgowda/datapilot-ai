"use client";

import { useEffect, useRef } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { Variants } from "framer-motion";
import { AlertTriangle, Bot, Zap } from "lucide-react";
import { cn } from "@/lib/utils";
import { AgentApprovalCard } from "./AgentApprovalCard";
import { AgentExplainPanel } from "./AgentExplainPanel";
import { AgentThinkingIndicator } from "./AgentThinkingIndicator";
import type {
  AgentConversationTurn,
  AgentErrorTurn,
  AgentResponseTurn,
  AgentUserTurn,
} from "./types";

// ── Empty-state goal suggestions ──────────────────────────────────────────────

const GOAL_EXAMPLES = [
  "Analyze my dataset and show top 5 categories",
  "Forecast revenue for the next 6 months",
  "Find rows with anomalies or outliers",
  "Generate a full report of the data",
  "Show correlations between all columns",
  "Update inactive records to active status",
];

const cardVariants: Variants = {
  hidden: { opacity: 0, y: 10 },
  show: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.2, ease: "easeOut", delay: i * 0.04 },
  }),
};

function EmptyState({ onExample }: { onExample: (q: string) => void }) {
  return (
    <div className="flex flex-col items-center text-center w-full px-6 py-16">
      {/* Gradient avatar */}
      <motion.div
        initial={{ opacity: 0, scale: 0.8 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.3, ease: "easeOut" }}
        className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-primary elevation-glow mb-6"
        aria-hidden="true"
      >
        <Bot className="h-7 w-7 text-white" />
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25, delay: 0.05, ease: "easeOut" }}
        className="space-y-2"
      >
        <h3 className="text-xl font-semibold text-foreground tracking-tight">
          Universal Data Agent
        </h3>
        <p className="text-sm text-muted-foreground max-w-xs leading-relaxed">
          Describe a goal — the agent plans and executes multi-step analysis.
          CRUD operations always require your approval.
        </p>
      </motion.div>

      {/* Suggestion cards 2×3 */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.2, delay: 0.2 }}
        className="mt-8 grid grid-cols-2 gap-2.5 w-full max-w-[480px]"
        role="list"
        aria-label="Example goals"
      >
        {GOAL_EXAMPLES.map((q, i) => (
          <motion.button
            key={q}
            custom={i}
            variants={cardVariants}
            initial="hidden"
            animate="show"
            role="listitem"
            onClick={() => onExample(q)}
            className={cn(
              "group rounded-xl border border-border/50 bg-card/60 px-4 py-3.5 text-left",
              "text-sm text-muted-foreground leading-snug",
              "hover:border-primary/30 hover:bg-card hover:text-foreground",
              "hover:elevation-sm transition-all duration-150",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            )}
          >
            {q}
          </motion.button>
        ))}
      </motion.div>
    </div>
  );
}

// ── Turn renderers ────────────────────────────────────────────────────────────

function UserBubble({ turn }: { turn: AgentUserTurn }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: "easeOut" }}
      className="flex justify-end"
    >
      <div className="max-w-[65%] rounded-2xl bg-primary px-4 py-3">
        <p className="text-sm text-primary-foreground whitespace-pre-wrap leading-relaxed">
          {turn.content}
        </p>
      </div>
    </motion.div>
  );
}

function AgentBubble({ turn }: { turn: AgentResponseTurn }) {
  const failed = turn.status === "failed";

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22, ease: "easeOut" }}
      className="flex items-start gap-3"
    >
      {/* Avatar */}
      <div
        className={cn(
          "mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full",
          failed ? "bg-destructive/10" : "bg-gradient-primary elevation-glow-sm"
        )}
        aria-hidden="true"
      >
        {failed ? (
          <AlertTriangle className="h-3 w-3 text-destructive" />
        ) : (
          <Zap className="h-3 w-3 text-white" />
        )}
      </div>

      {/* Ambient content — text directly on background */}
      <div className="flex-1 min-w-0 space-y-2">
        <p
          className={cn(
            "text-sm leading-[1.8] whitespace-pre-wrap",
            failed ? "text-destructive" : "text-foreground"
          )}
        >
          {failed && turn.error ? turn.error : turn.answer || "Done."}
        </p>

        {turn.steps.length > 0 && !failed && (
          <p className="text-[11px] text-muted-foreground/40 flex items-center gap-1">
            <Zap className="h-2.5 w-2.5" aria-hidden="true" />
            {turn.steps.length} tool call
            {turn.steps.length !== 1 ? "s" : ""} executed
          </p>
        )}
      </div>
    </motion.div>
  );
}

function ErrorBubble({ turn }: { turn: AgentErrorTurn }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: "easeOut" }}
      className="flex items-start gap-3"
    >
      <div
        className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-destructive/10"
        aria-hidden="true"
      >
        <AlertTriangle className="h-3 w-3 text-destructive" />
      </div>
      <div className="flex-1 min-w-0 rounded-xl border border-destructive/20 bg-destructive/5 px-4 py-3">
        <p className="text-sm text-destructive whitespace-pre-wrap">
          {turn.message}
        </p>
      </div>
    </motion.div>
  );
}

// ── Thread ────────────────────────────────────────────────────────────────────

interface AgentThreadProps {
  turns: AgentConversationTurn[];
  isPending: boolean;
  isResuming: boolean;
  onApprove: (sessionId: string) => void;
  onReject: (sessionId: string) => void;
  onExample: (q: string) => void;
}

export function AgentThread({
  turns,
  isPending,
  isResuming,
  onApprove,
  onReject,
  onExample,
}: AgentThreadProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns.length, isPending]);

  if (turns.length === 0 && !isPending) {
    return (
      <div
        className="flex-1 overflow-y-auto"
        role="region"
        aria-label="Agent conversation"
      >
        <EmptyState onExample={onExample} />
      </div>
    );
  }

  return (
    <div
      className="flex-1 overflow-y-auto"
      role="log"
      aria-label="Agent conversation"
      aria-live="polite"
      aria-relevant="additions"
    >
      <div className="max-w-2xl mx-auto px-6 py-8 space-y-8">
        <AnimatePresence initial={false}>
          {turns.map((turn) => {
            switch (turn.role) {
              case "user":
                return <UserBubble key={turn.id} turn={turn} />;
              case "agent":
                return <AgentBubble key={turn.id} turn={turn} />;
              case "approval":
                return (
                  <AgentApprovalCard
                    key={turn.id}
                    approval={turn.approval}
                    isResuming={isResuming}
                    onApprove={() => onApprove(turn.sessionId)}
                    onReject={() => onReject(turn.sessionId)}
                  />
                );
              case "explain":
                return <AgentExplainPanel key={turn.id} turn={turn} />;
              case "error":
                return <ErrorBubble key={turn.id} turn={turn} />;
              default:
                return null;
            }
          })}
        </AnimatePresence>

        <AnimatePresence>
          {isPending && <AgentThinkingIndicator key="thinking" />}
        </AnimatePresence>

        <div ref={bottomRef} aria-hidden="true" />
      </div>
    </div>
  );
}
