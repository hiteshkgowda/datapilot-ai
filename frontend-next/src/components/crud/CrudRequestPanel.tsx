"use client";

import { useCallback, useRef, useState } from "react";
import { motion } from "framer-motion";
import type { Variants } from "framer-motion";
import {
  ArrowRight,
  Database,
  Loader2,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import type { ConnectionMetadata } from "@/lib/api/types";

const MAX_CHARS = 600;

const EXAMPLES = [
  "Update all inactive users to active",
  "Delete orders older than 2022",
  "Create a new customer named John",
  "Set status = 'shipped' where order_id = 42",
  "Soft delete products with stock = 0",
];

const chipVariants: Variants = {
  hidden: { opacity: 0, y: 6 },
  show: { opacity: 1, y: 0 },
};

interface CrudRequestPanelProps {
  connections: ConnectionMetadata[];
  connectionId: string;
  onConnectionChange: (id: string) => void;
  onSubmit: (question: string) => void;
  isPending: boolean;
}

export function CrudRequestPanel({
  connections,
  connectionId,
  onConnectionChange,
  onSubmit,
  isPending,
}: CrudRequestPanelProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const autoResize = useCallback((el: HTMLTextAreaElement) => {
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
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
    if (!trimmed || isPending || !connectionId) return;
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

  const canSubmit = value.trim().length > 0 && !isPending && !!connectionId;
  const remaining = MAX_CHARS - value.length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10">
          <ShieldCheck className="h-5 w-5 text-primary" aria-hidden="true" />
        </div>
        <div>
          <h1 className="text-base font-semibold text-foreground">CRUD Workspace</h1>
          <p className="text-xs text-muted-foreground">
            Safe AI-assisted database operations
          </p>
        </div>
      </div>

      {/* Connection selector */}
      <div className="space-y-2">
        <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide flex items-center gap-1.5">
          <Database className="h-3 w-3" aria-hidden="true" />
          Database connection
        </label>

        {connections.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border/50 bg-muted/20 px-4 py-3">
            <p className="text-xs text-muted-foreground">
              No connections available.{" "}
              <a
                href="/connections"
                className="text-primary hover:underline"
              >
                Add a connection
              </a>{" "}
              first.
            </p>
          </div>
        ) : (
          <select
            value={connectionId}
            onChange={(e) => onConnectionChange(e.target.value)}
            disabled={isPending}
            className={cn(
              "w-full rounded-lg border border-border/60 bg-card/60 px-3 py-2",
              "text-sm text-foreground",
              "focus:outline-none focus:border-primary/50 transition-colors",
              "disabled:opacity-50 disabled:cursor-not-allowed",
              "appearance-none cursor-pointer"
            )}
            aria-label="Select database connection"
          >
            <option value="">— Select a connection —</option>
            {connections.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} ({c.db_type})
              </option>
            ))}
          </select>
        )}
      </div>

      {/* Request input */}
      <div className="space-y-2">
        <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          Request
        </label>

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
              !connectionId
                ? "Select a connection above first…"
                : isPending
                ? "Processing…"
                : "Describe the data change in plain English… (Enter to preview)"
            }
            disabled={isPending || !connectionId}
            rows={3}
            aria-label="CRUD request in natural language"
            className={cn(
              "w-full resize-none bg-transparent px-4 pt-4 pb-2",
              "text-sm text-foreground placeholder:text-muted-foreground/50",
              "focus:outline-none rounded-t-xl",
              "disabled:opacity-50 disabled:cursor-not-allowed",
              "min-h-[80px] max-h-[200px] leading-relaxed"
            )}
            style={{ overflowY: "auto" }}
          />

          <div className="flex items-center justify-between px-4 pb-3">
            <p className="text-[10px] text-muted-foreground/40">
              Shift+Enter for new line · always previewed before execution
            </p>
            <div className="flex items-center gap-2">
              {remaining < 120 && (
                <span
                  className={cn(
                    "text-[10px] tabular-nums",
                    remaining < 30
                      ? "text-destructive"
                      : "text-muted-foreground/60"
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
                  aria-label={isPending ? "Processing…" : "Preview operation"}
                >
                  {isPending ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      Previewing…
                    </>
                  ) : (
                    <>
                      Preview
                      <ArrowRight className="h-3.5 w-3.5" />
                    </>
                  )}
                </Button>
              </motion.div>
            </div>
          </div>
        </div>
      </div>

      {/* Example chips */}
      {!isPending && (
        <div className="space-y-2">
          <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground/60 uppercase tracking-wide">
            <Sparkles className="h-3 w-3" aria-hidden="true" />
            Try an example
          </div>
          <motion.div
            className="flex flex-wrap gap-2"
            variants={{ show: { transition: { staggerChildren: 0.05 } } }}
            initial="hidden"
            animate="show"
          >
            {EXAMPLES.map((q) => (
              <motion.button
                key={q}
                variants={chipVariants}
                onClick={() => setExample(q)}
                disabled={!connectionId || isPending}
                className={cn(
                  "rounded-full border border-border/50 bg-card/40 px-3 py-1.5",
                  "text-xs text-muted-foreground hover:text-foreground hover:border-primary/40 hover:bg-primary/5",
                  "transition-colors duration-150 text-left",
                  "disabled:opacity-40 disabled:cursor-not-allowed"
                )}
              >
                {q}
              </motion.button>
            ))}
          </motion.div>
        </div>
      )}

      {/* Safety note */}
      <div className="rounded-lg border border-border/30 bg-muted/20 px-4 py-3">
        <p className="text-[11px] text-muted-foreground leading-relaxed">
          <span className="font-medium text-foreground">Safe by design:</span> every
          operation is previewed and requires your explicit approval before any
          data is changed. Destructive operations always require confirmation.
        </p>
      </div>
    </div>
  );
}
