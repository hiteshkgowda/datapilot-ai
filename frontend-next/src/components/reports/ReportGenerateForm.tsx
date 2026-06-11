"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { Loader2, Plus, Sparkles, Trash2, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { useDatasets } from "@/hooks/use-datasets";
import { useGenerateReport } from "@/hooks/use-reports";
import type { ReportMetadata } from "@/lib/api/types";

const MAX_QUESTIONS = 5;

interface ReportGenerateFormProps {
  /** Pre-select a dataset; if undefined the user can choose from dropdown */
  defaultDatasetId?: string;
  onGenerated?: (report: ReportMetadata) => void;
}

export function ReportGenerateForm({
  defaultDatasetId,
  onGenerated,
}: ReportGenerateFormProps) {
  const { data } = useDatasets();
  const datasets = data?.datasets ?? [];

  const [datasetId, setDatasetId] = useState(defaultDatasetId ?? "");
  const [questions, setQuestions] = useState<string[]>([]);
  const [draft, setDraft] = useState("");

  const { mutate, isPending } = useGenerateReport();

  function addQuestion() {
    const trimmed = draft.trim();
    if (!trimmed || questions.length >= MAX_QUESTIONS) return;
    setQuestions((q) => [...q, trimmed]);
    setDraft("");
  }

  function removeQuestion(i: number) {
    setQuestions((q) => q.filter((_, idx) => idx !== i));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!datasetId || isPending) return;
    mutate({ datasetId, questions }, { onSuccess: onGenerated });
  }

  const canSubmit = datasetId.length > 0 && !isPending;

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-xl border border-border/50 bg-card/60 backdrop-blur-sm p-5 space-y-4"
    >
      <div className="flex items-center gap-2">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/10">
          <Sparkles className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
        </div>
        <h2 className="text-sm font-semibold text-foreground">Generate Report</h2>
      </div>

      {/* Dataset selector */}
      {!defaultDatasetId && (
        <div className="space-y-1.5">
          <label
            htmlFor="dataset-select"
            className="text-xs text-muted-foreground"
          >
            Dataset
          </label>
          <select
            id="dataset-select"
            value={datasetId}
            onChange={(e) => setDatasetId(e.target.value)}
            disabled={isPending}
            className={cn(
              "w-full rounded-lg border border-border/50 bg-background/60 px-3 py-2",
              "text-sm text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              "disabled:opacity-50"
            )}
          >
            <option value="">Select a dataset…</option>
            {datasets.map((ds) => (
              <option key={ds.id} value={ds.id}>
                {ds.filename}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* AI questions */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <label className="text-xs text-muted-foreground">
            AI questions{" "}
            <span className="text-muted-foreground/50">(optional)</span>
          </label>
          <span className="text-[10px] text-muted-foreground/50">
            {questions.length}/{MAX_QUESTIONS}
          </span>
        </div>

        {/* Existing questions */}
        {questions.length > 0 && (
          <ul className="space-y-1.5">
            {questions.map((q, i) => (
              <motion.li
                key={i}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                className="flex items-start gap-2 rounded-lg bg-muted/20 px-3 py-2 text-xs"
              >
                <span className="flex-1 text-foreground">{q}</span>
                <button
                  type="button"
                  onClick={() => removeQuestion(i)}
                  className="shrink-0 text-muted-foreground hover:text-destructive transition-colors"
                  aria-label={`Remove question ${i + 1}`}
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </motion.li>
            ))}
          </ul>
        )}

        {/* Add question input */}
        {questions.length < MAX_QUESTIONS && (
          <div className="flex gap-2">
            <input
              type="text"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  addQuestion();
                }
              }}
              placeholder="Add an AI-generated question…"
              disabled={isPending}
              className={cn(
                "flex-1 rounded-lg border border-border/50 bg-background/60 px-3 py-2",
                "text-xs text-foreground placeholder:text-muted-foreground/40",
                "focus:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                "disabled:opacity-50"
              )}
            />
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="h-8 w-8 p-0 shrink-0"
              onClick={addQuestion}
              disabled={!draft.trim() || isPending}
              aria-label="Add question"
            >
              <Plus className="h-4 w-4" />
            </Button>
          </div>
        )}

        <p className="text-[10px] text-muted-foreground/50">
          Each question adds an AI-generated section to the report. Leave empty
          for a fully deterministic report.
        </p>
      </div>

      {/* Submit */}
      <Button
        type="submit"
        disabled={!canSubmit}
        className="w-full gap-2"
      >
        {isPending ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" />
            Generating report…
          </>
        ) : (
          <>
            <Sparkles className="h-4 w-4" />
            Generate PDF Report
          </>
        )}
      </Button>

      {isPending && (
        <p className="text-center text-[11px] text-muted-foreground/60 animate-pulse">
          Analyzing data and building PDF… this may take up to 60 s
        </p>
      )}
    </form>
  );
}
