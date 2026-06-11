"use client";

import { useEffect, useRef } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { Variants } from "framer-motion";
import { BarChart2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { UserMessage } from "./UserMessage";
import { AssistantMessage, ErrorMessage } from "./AssistantMessage";
import { TypingIndicator } from "./TypingIndicator";
import type { ConversationTurn } from "./types";

// ── Suggestion questions used in the empty state ──────────────────────────────

const SUGGESTIONS = [
  "What are the top 10 rows?",
  "Show average values by category",
  "Find rows with the highest values",
  "Create a bar chart of the data",
  "Calculate correlations between columns",
  "Group by the first column and sum totals",
];

// ── Empty state ───────────────────────────────────────────────────────────────

const cardVariants: Variants = {
  hidden: { opacity: 0, y: 12 },
  show: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.22, ease: "easeOut", delay: i * 0.04 },
  }),
};

interface EmptyStateProps {
  filename: string;
  columnNames: string[];
  rowCount: number;
  onExample: (q: string) => void;
}

function EmptyState({
  filename,
  columnNames,
  rowCount,
  onExample,
}: EmptyStateProps) {
  const showMeta = rowCount > 0 || columnNames.length > 0;
  const visibleCols = columnNames.slice(0, 8);
  const hiddenColCount = columnNames.length - visibleCols.length;

  return (
    <div className="flex flex-col items-center text-center w-full px-6 py-16">
      {/* Icon */}
      <motion.div
        initial={{ opacity: 0, scale: 0.8 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.3, ease: "easeOut" }}
        className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10 mb-6"
      >
        <BarChart2 className="h-7 w-7 text-primary" aria-hidden="true" />
      </motion.div>

      {/* Title */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25, delay: 0.05, ease: "easeOut" }}
        className="space-y-0.5"
      >
        <h3 className="text-xl font-semibold text-foreground tracking-tight">
          Ask anything about
        </h3>
        <p
          className="text-xl font-semibold text-primary truncate max-w-[400px]"
          title={filename}
        >
          {filename}
        </p>
      </motion.div>

      {/* Dataset stats */}
      {showMeta && (
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.2, delay: 0.12 }}
          className="mt-2 text-sm text-muted-foreground"
        >
          {rowCount > 0 && (
            <span>{rowCount.toLocaleString()} rows</span>
          )}
          {rowCount > 0 && columnNames.length > 0 && (
            <span className="mx-1.5 text-muted-foreground/30">·</span>
          )}
          {columnNames.length > 0 && (
            <span>{columnNames.length} columns</span>
          )}
        </motion.p>
      )}

      {/* Column pills */}
      {visibleCols.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.22, delay: 0.18 }}
          className="mt-4 flex flex-wrap justify-center gap-1.5 max-w-lg"
        >
          {visibleCols.map((col) => (
            <span
              key={col}
              className={cn(
                "rounded-full border border-border/60 bg-muted/40 px-2.5 py-0.5",
                "text-[11px] font-mono text-muted-foreground/80"
              )}
            >
              {col}
            </span>
          ))}
          {hiddenColCount > 0 && (
            <span className="rounded-full border border-border/40 bg-muted/20 px-2.5 py-0.5 text-[11px] text-muted-foreground/40">
              +{hiddenColCount} more
            </span>
          )}
        </motion.div>
      )}

      {/* Suggestion cards — 2×3 grid */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.2, delay: 0.25 }}
        className="mt-8 grid grid-cols-2 gap-2.5 w-full max-w-[480px]"
        role="list"
        aria-label="Suggested questions"
      >
        {SUGGESTIONS.map((q, i) => (
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

// ── Conversation thread ───────────────────────────────────────────────────────

interface ConversationThreadProps {
  turns: ConversationTurn[];
  isPending: boolean;
  filename: string;
  columnNames: string[];
  rowCount: number;
  onExample: (q: string) => void;
}

export function ConversationThread({
  turns,
  isPending,
  filename,
  columnNames,
  rowCount,
  onExample,
}: ConversationThreadProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, isPending]);

  if (turns.length === 0 && !isPending) {
    return (
      <div className="flex-1 overflow-y-auto" role="region" aria-label="Conversation">
        <EmptyState
          filename={filename}
          columnNames={columnNames}
          rowCount={rowCount}
          onExample={onExample}
        />
      </div>
    );
  }

  return (
    <div
      className="flex-1 overflow-y-auto"
      role="log"
      aria-label="Conversation"
      aria-live="polite"
      aria-relevant="additions"
    >
      {/* Centered conversation column */}
      <div className="max-w-3xl mx-auto px-6 py-8 space-y-8">
        <AnimatePresence initial={false}>
          {turns.map((turn) => {
            if (turn.role === "user") {
              return <UserMessage key={turn.id} turn={turn} />;
            }
            if (turn.role === "assistant") {
              return <AssistantMessage key={turn.id} turn={turn} />;
            }
            return <ErrorMessage key={turn.id} turn={turn} />;
          })}
        </AnimatePresence>

        <AnimatePresence>
          {isPending && <TypingIndicator key="typing" />}
        </AnimatePresence>

        <div ref={bottomRef} aria-hidden="true" />
      </div>
    </div>
  );
}
