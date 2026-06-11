"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { Variants } from "framer-motion";
import { ArrowUp, ChevronDown, Loader2, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import type { AgentContext } from "./types";

const MAX_CHARS = 800;

const EXAMPLES = [
  "Analyze top categories",
  "Forecast next 6 months",
  "Generate PDF report",
  "Find anomalies",
  "Update inactive records",
  "Show correlations",
];

const chipVariants: Variants = {
  hidden: { opacity: 0, y: 6 },
  show: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.18, ease: "easeOut", delay: i * 0.03 },
  }),
  exit: { opacity: 0, y: 4, transition: { duration: 0.1 } },
};

interface AgentGoalInputProps {
  onRun: (goal: string, ctx: Partial<AgentContext>) => void;
  onExplain: (goal: string, ctx: Partial<AgentContext>) => void;
  isPending: boolean;
  prefill?: string;
  onPrefillConsumed?: () => void;
}

export function AgentGoalInput({
  onRun,
  onExplain,
  isPending,
  prefill,
  onPrefillConsumed,
}: AgentGoalInputProps) {
  const [value, setValue] = useState("");
  const [showContext, setShowContext] = useState(false);
  const [datasetId, setDatasetId] = useState("");
  const [connectionId, setConnectionId] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!prefill) return;
    setValue(prefill);
    onPrefillConsumed?.();
    setTimeout(() => {
      const el = textareaRef.current;
      if (el) {
        el.focus();
        el.style.height = "auto";
        el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
      }
    }, 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefill]);

  const autoResize = useCallback((el: HTMLTextAreaElement) => {
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, []);

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const next = e.target.value.slice(0, MAX_CHARS);
    setValue(next);
    autoResize(e.target);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  function buildCtx(): Partial<AgentContext> {
    const ctx: Partial<AgentContext> = {};
    if (datasetId.trim()) ctx.datasetId = datasetId.trim();
    if (connectionId.trim()) ctx.connectionId = connectionId.trim();
    return ctx;
  }

  const submit = () => {
    const trimmed = value.trim();
    if (!trimmed || isPending) return;
    onRun(trimmed, buildCtx());
    setValue("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  };

  const explain = () => {
    const trimmed = value.trim();
    if (!trimmed || isPending) return;
    onExplain(trimmed, buildCtx());
  };

  const setExample = (q: string) => {
    setValue(q);
    setTimeout(() => {
      if (textareaRef.current) {
        autoResize(textareaRef.current);
        textareaRef.current.focus();
      }
    }, 0);
  };

  const canSend = value.trim().length > 0 && !isPending;
  const remaining = MAX_CHARS - value.length;
  const showSuggestions = value.length === 0 && !isPending;

  return (
    <div
      className={cn(
        "shrink-0 border-t border-border/40",
        "bg-background/90 backdrop-blur-md"
      )}
    >
      <div className="max-w-2xl mx-auto px-4 py-3 space-y-2.5">
        {/* Context disclosure */}
        <AnimatePresence>
          {showContext && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.2 }}
              className="overflow-hidden"
            >
              <div className="grid grid-cols-2 gap-2 pb-1">
                <div>
                  <label className="text-[10px] text-muted-foreground uppercase tracking-wide block mb-1">
                    Dataset ID (optional)
                  </label>
                  <input
                    type="text"
                    value={datasetId}
                    onChange={(e) => setDatasetId(e.target.value)}
                    placeholder="e.g. abc123"
                    className={cn(
                      "w-full rounded-lg border border-border/60 bg-card/60 px-3 py-1.5",
                      "text-xs font-mono placeholder:text-muted-foreground/40",
                      "focus:outline-none focus:border-primary/50 transition-colors"
                    )}
                  />
                </div>
                <div>
                  <label className="text-[10px] text-muted-foreground uppercase tracking-wide block mb-1">
                    Connection ID (optional)
                  </label>
                  <input
                    type="text"
                    value={connectionId}
                    onChange={(e) => setConnectionId(e.target.value)}
                    placeholder="e.g. conn-xyz"
                    className={cn(
                      "w-full rounded-lg border border-border/60 bg-card/60 px-3 py-1.5",
                      "text-xs font-mono placeholder:text-muted-foreground/40",
                      "focus:outline-none focus:border-primary/50 transition-colors"
                    )}
                  />
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Suggestion chips */}
        <AnimatePresence>
          {showSuggestions && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0, transition: { duration: 0.1 } }}
              className="flex items-center gap-2 overflow-x-auto pb-0.5"
              style={{ scrollbarWidth: "none" }}
              aria-label="Example goals"
            >
              {EXAMPLES.map((q, i) => (
                <motion.button
                  key={q}
                  custom={i}
                  variants={chipVariants}
                  initial="hidden"
                  animate="show"
                  exit="exit"
                  onClick={() => setExample(q)}
                  className={cn(
                    "flex-shrink-0 flex items-center gap-1.5 rounded-full border border-border/60 bg-muted/30",
                    "px-3 py-1 text-[11px] text-muted-foreground/70",
                    "hover:border-primary/30 hover:bg-muted/60 hover:text-foreground",
                    "transition-colors duration-150",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  )}
                >
                  <Sparkles className="h-2.5 w-2.5 shrink-0" aria-hidden="true" />
                  {q}
                </motion.button>
              ))}
            </motion.div>
          )}
        </AnimatePresence>

        {/* Composer */}
        <div
          className={cn(
            "flex items-end gap-2 rounded-2xl border transition-all duration-150",
            "bg-card/60 backdrop-blur-sm",
            isPending
              ? "border-border/40"
              : [
                  "border-border/60",
                  "focus-within:border-primary/50",
                  "focus-within:elevation-glow-sm",
                ].join(" ")
          )}
        >
          <textarea
            ref={textareaRef}
            value={value}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            placeholder={
              isPending
                ? "Agent is running…"
                : "Describe a goal… (Enter to run)"
            }
            disabled={isPending}
            rows={1}
            aria-label="Agent goal"
            className={cn(
              "flex-1 resize-none bg-transparent px-4 py-3.5",
              "text-sm text-foreground placeholder:text-muted-foreground/40",
              "focus:outline-none",
              "disabled:opacity-40 disabled:cursor-not-allowed",
              "min-h-[50px] max-h-[160px] leading-relaxed"
            )}
            style={{ overflowY: "auto" }}
          />

          <div className="flex items-center gap-1.5 px-3 pb-3 shrink-0">
            {remaining < 150 && (
              <span
                className={cn(
                  "text-[10px] tabular-nums",
                  remaining < 50 ? "text-destructive" : "text-muted-foreground/40"
                )}
              >
                {remaining}
              </span>
            )}

            {/* Explain button */}
            <Button
              variant="ghost"
              size="sm"
              className="h-8 gap-1.5 text-xs text-muted-foreground hover:text-foreground px-2"
              disabled={!canSend}
              onClick={explain}
              title="Preview the agent's plan without executing"
            >
              <Sparkles className="h-3 w-3" aria-hidden="true" />
              Explain
            </Button>

            {/* Context toggle */}
            <Button
              variant="ghost"
              size="sm"
              className={cn(
                "h-8 gap-1 text-xs px-2",
                showContext
                  ? "text-primary"
                  : "text-muted-foreground hover:text-foreground"
              )}
              onClick={() => setShowContext((v) => !v)}
              title="Add dataset / connection context"
            >
              <ChevronDown
                className={cn(
                  "h-3 w-3 transition-transform duration-200",
                  showContext && "rotate-180"
                )}
                aria-hidden="true"
              />
              Context
            </Button>

            {/* Send button */}
            <motion.div whileTap={{ scale: 0.9 }}>
              <Button
                size="icon"
                className={cn(
                  "h-8 w-8 rounded-xl transition-all",
                  canSend ? "elevation-glow-sm" : ""
                )}
                disabled={!canSend}
                onClick={submit}
                aria-label={isPending ? "Running…" : "Run agent"}
              >
                {isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                ) : (
                  <ArrowUp className="h-4 w-4" aria-hidden="true" />
                )}
              </Button>
            </motion.div>
          </div>
        </div>

        <p className="text-center text-[10px] text-muted-foreground/30">
          Shift+Enter for new line · CRUD operations always require approval
        </p>
      </div>
    </div>
  );
}
