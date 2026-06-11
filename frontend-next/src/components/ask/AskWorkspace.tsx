"use client";

import { useCallback, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Database, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { DatasetSelector } from "./DatasetSelector";
import { ConversationThread } from "./ConversationThread";
import { QuestionInput } from "./QuestionInput";
import { useAsk } from "@/hooks/use-ask";
import { useDatasetPreview } from "@/hooks/use-datasets";

interface AskWorkspaceProps {
  datasetId: string;
}

export function AskWorkspace({ datasetId }: AskWorkspaceProps) {
  const { turns, sendQuestion, clearHistory, isPending } = useAsk(datasetId);
  const { data: preview } = useDatasetPreview(datasetId);

  const [prefill, setPrefill] = useState<string | undefined>();

  const handleExample = useCallback((q: string) => {
    setPrefill(q);
  }, []);

  const filename = preview?.filename ?? "Dataset";
  const columnNames = preview?.column_names ?? [];
  const rowCount = preview?.rows ?? 0;

  return (
    <div className="flex flex-col h-full bg-background">
      {/* ── Header ─────────────────────────────────────────────────── */}
      <header
        className={cn(
          "flex h-11 shrink-0 items-center justify-between",
          "border-b border-border/40 bg-background/95 backdrop-blur-sm",
          "px-3"
        )}
      >
        {/* Left: back + dataset selector */}
        <div className="flex items-center gap-1 min-w-0">
          <Link
            href="/datasets"
            aria-label="Back to datasets"
            className={cn(
              "flex h-7 w-7 items-center justify-center rounded-lg",
              "text-muted-foreground hover:text-foreground hover:bg-muted/50",
              "transition-colors duration-150",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            )}
          >
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          </Link>

          <div className="h-4 w-px bg-border/60 mx-1 shrink-0" aria-hidden="true" />

          {/* Dataset icon */}
          <div
            className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-primary/10"
            aria-hidden="true"
          >
            <Database className="h-3 w-3 text-primary" />
          </div>

          <DatasetSelector currentId={datasetId} />
        </div>

        {/* Right: stats + clear */}
        <div className="flex items-center gap-2 shrink-0">
          {preview && (
            <span className="hidden sm:block text-xs text-muted-foreground/50 tabular-nums">
              {rowCount.toLocaleString()} rows
              <span className="mx-1 text-muted-foreground/25">·</span>
              {columnNames.length} cols
            </span>
          )}

          {turns.length > 0 && (
            <>
              <div className="h-4 w-px bg-border/60" aria-hidden="true" />
              <button
                onClick={clearHistory}
                className={cn(
                  "flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs",
                  "text-muted-foreground/60 hover:text-foreground hover:bg-muted/50",
                  "transition-colors duration-150",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                )}
                title="Clear conversation history"
              >
                <Trash2 className="h-3 w-3" aria-hidden="true" />
                <span className="hidden sm:inline">Clear</span>
              </button>
            </>
          )}
        </div>
      </header>

      {/* ── Conversation thread ─────────────────────────────────────── */}
      <ConversationThread
        turns={turns}
        isPending={isPending}
        filename={filename}
        columnNames={columnNames}
        rowCount={rowCount}
        onExample={handleExample}
      />

      {/* ── Input bar ──────────────────────────────────────────────── */}
      <QuestionInput
        onSend={sendQuestion}
        isPending={isPending}
        prefill={prefill}
        onPrefillConsumed={() => setPrefill(undefined)}
      />
    </div>
  );
}
