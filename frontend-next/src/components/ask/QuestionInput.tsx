"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { Variants } from "framer-motion";
import { ArrowUp, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

const MAX_CHARS = 500;

const QUICK_SUGGESTIONS = [
  "Top 10 rows",
  "Average by category",
  "Distribution chart",
  "Show correlations",
  "Group by month",
  "Find outliers",
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

interface QuestionInputProps {
  onSend: (question: string) => void;
  isPending: boolean;
  prefill?: string;
  onPrefillConsumed?: () => void;
}

export function QuestionInput({
  onSend,
  isPending,
  prefill,
  onPrefillConsumed,
}: QuestionInputProps) {
  const [value, setValue] = useState("");
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

  const submit = () => {
    const trimmed = value.trim();
    if (!trimmed || isPending) return;
    onSend(trimmed);
    setValue("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
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
      <div className="max-w-3xl mx-auto px-4 py-3 space-y-2.5">
        {/* ── Quick suggestions ────────────────────────────────────── */}
        <AnimatePresence>
          {showSuggestions && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0, transition: { duration: 0.1 } }}
              className="flex items-center gap-2 overflow-x-auto pb-0.5"
              style={{ scrollbarWidth: "none" }}
              aria-label="Quick suggestions"
            >
              {QUICK_SUGGESTIONS.map((s, i) => (
                <motion.button
                  key={s}
                  custom={i}
                  variants={chipVariants}
                  initial="hidden"
                  animate="show"
                  exit="exit"
                  onClick={() => setExample(s)}
                  className={cn(
                    "flex-shrink-0 rounded-full border border-border/60 bg-muted/30",
                    "px-3 py-1 text-[11px] text-muted-foreground/70",
                    "hover:border-primary/30 hover:bg-muted/60 hover:text-foreground",
                    "transition-colors duration-150",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  )}
                >
                  {s}
                </motion.button>
              ))}
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Composer ─────────────────────────────────────────────── */}
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
                ? "Analyzing…"
                : "Ask anything about this dataset…"
            }
            disabled={isPending}
            rows={1}
            aria-label="Question input"
            className={cn(
              "flex-1 resize-none bg-transparent px-4 py-3.5",
              "text-sm text-foreground placeholder:text-muted-foreground/40",
              "focus:outline-none",
              "disabled:opacity-40 disabled:cursor-not-allowed",
              "min-h-[50px] max-h-[160px] leading-relaxed"
            )}
            style={{ overflowY: "auto" }}
          />

          <div className="flex items-center gap-2 px-3 pb-3 shrink-0">
            {remaining < 80 && (
              <span
                className={cn(
                  "text-[10px] tabular-nums",
                  remaining < 20 ? "text-destructive" : "text-muted-foreground/40"
                )}
              >
                {remaining}
              </span>
            )}

            <motion.div whileTap={{ scale: 0.9 }}>
              <Button
                size="icon"
                className={cn(
                  "h-8 w-8 rounded-xl transition-all",
                  canSend ? "elevation-glow-sm" : ""
                )}
                disabled={!canSend}
                onClick={submit}
                aria-label={isPending ? "Analyzing…" : "Send question"}
              >
                {isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <ArrowUp className="h-4 w-4" />
                )}
              </Button>
            </motion.div>
          </div>
        </div>

        {/* ── Hint ─────────────────────────────────────────────────── */}
        <p className="text-center text-[10px] text-muted-foreground/30">
          Shift+Enter for new line · results in 10–60 s with a local model
        </p>
      </div>
    </div>
  );
}
