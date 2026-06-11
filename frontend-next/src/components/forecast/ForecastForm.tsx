"use client";

import { useCallback, useRef, useState } from "react";
import { motion } from "framer-motion";
import type { Variants } from "framer-motion";
import { ArrowRight, Loader2, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

const MAX_CHARS = 500;

const EXAMPLES = [
  "Forecast sales for the next 6 months",
  "Detect anomalies in revenue over time",
  "Show monthly trend with confidence intervals",
  "What will demand look like next quarter?",
];

const chipVariants: Variants = {
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0 },
};

interface ForecastFormProps {
  onSubmit: (question: string) => void;
  isPending: boolean;
  /** Re-run with a new question resets the result */
  hasResult: boolean;
}

export function ForecastForm({ onSubmit, isPending, hasResult }: ForecastFormProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

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
    onSubmit(trimmed);
    setValue("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
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

  const canSubmit = value.trim().length > 0 && !isPending;
  const remaining = MAX_CHARS - value.length;

  return (
    <div className="space-y-4">
      {/* Input area */}
      <div
        className={cn(
          "rounded-xl border bg-card/60 backdrop-blur-sm transition-colors duration-150",
          isPending
            ? "border-border/40"
            : "border-border/60 focus-within:border-primary/50"
        )}
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder={
            isPending
              ? "Running forecast…"
              : "Ask a forecasting question… (Enter to run, Shift+Enter for newline)"
          }
          disabled={isPending}
          rows={3}
          aria-label="Forecast question"
          className={cn(
            "w-full resize-none bg-transparent px-4 pt-4 pb-2",
            "text-sm text-foreground placeholder:text-muted-foreground/50",
            "focus:outline-none rounded-t-xl",
            "disabled:opacity-50 disabled:cursor-not-allowed",
            "min-h-[80px] max-h-[160px] leading-relaxed"
          )}
          style={{ overflowY: "auto" }}
        />

        <div className="flex items-center justify-between px-4 pb-3">
          <p className="text-[10px] text-muted-foreground/40">
            Shift+Enter for new line · results may take 10–60 s
          </p>
          <div className="flex items-center gap-2">
            {remaining < 100 && (
              <span
                className={cn(
                  "text-[10px] tabular-nums",
                  remaining < 20 ? "text-destructive" : "text-muted-foreground/60"
                )}
              >
                {remaining}
              </span>
            )}
            <motion.div whileTap={{ scale: 0.92 }}>
              <Button
                size="sm"
                className="h-8 gap-1.5"
                disabled={!canSubmit}
                onClick={submit}
                aria-label={isPending ? "Running…" : "Run forecast"}
              >
                {isPending ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    Running…
                  </>
                ) : (
                  <>
                    {hasResult ? "Re-run" : "Run forecast"}
                    <ArrowRight className="h-3.5 w-3.5" />
                  </>
                )}
              </Button>
            </motion.div>
          </div>
        </div>
      </div>

      {/* Example chips — only shown when idle and no result yet */}
      {!hasResult && !isPending && (
        <div className="space-y-2">
          <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground/60 uppercase tracking-wide">
            <Sparkles className="h-3 w-3" aria-hidden="true" />
            Try an example
          </div>
          <motion.div
            className="flex flex-wrap gap-2"
            variants={{ show: { transition: { staggerChildren: 0.06 } } }}
            initial="hidden"
            animate="show"
          >
            {EXAMPLES.map((q) => (
              <motion.button
                key={q}
                variants={chipVariants}
                onClick={() => setExample(q)}
                className={cn(
                  "rounded-full border border-border/50 bg-card/40 px-3 py-1.5",
                  "text-xs text-muted-foreground hover:text-foreground hover:border-primary/40 hover:bg-primary/5",
                  "transition-colors duration-150 text-left"
                )}
              >
                {q}
              </motion.button>
            ))}
          </motion.div>
        </div>
      )}
    </div>
  );
}
