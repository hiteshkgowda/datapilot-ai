"use client";

import { useState } from "react";
import { Check, ChevronDown, ChevronUp, Copy, Table2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

const MAX_VISIBLE_ROWS = 10;

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") {
    return Number.isInteger(value)
      ? value.toLocaleString()
      : value.toPrecision(6);
  }
  const s = String(value);
  return s.length > 64 ? s.slice(0, 61) + "…" : s;
}

function isNumeric(value: unknown): boolean {
  return typeof value === "number";
}

function toCSV(columns: string[], data: Record<string, unknown>[]): string {
  const escape = (v: unknown) => {
    if (v === null || v === undefined) return "";
    const s = String(v);
    return s.includes(",") || s.includes('"') || s.includes("\n")
      ? `"${s.replace(/"/g, '""')}"`
      : s;
  };
  const header = columns.join(",");
  const rows = data.map((r) => columns.map((c) => escape(r[c])).join(","));
  return [header, ...rows].join("\n");
}

interface ResultTableProps {
  data: Record<string, unknown>[];
}

export function ResultTable({ data }: ResultTableProps) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  if (data.length === 0) return null;

  const columns = Object.keys(data[0]);
  const visibleRows = expanded ? data : data.slice(0, MAX_VISIBLE_ROWS);
  const hasMore = data.length > MAX_VISIBLE_ROWS;

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(toCSV(columns, data));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard access denied — ignore
    }
  }

  return (
    <div className="rounded-xl border border-border/60 bg-card overflow-hidden elevation-sm">
      {/* ── Card header ───────────────────────────────────────────── */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-border/40 bg-muted/20">
        <div className="flex items-center gap-2">
          <Table2 className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
          <span className="text-xs font-medium text-muted-foreground">
            {data.length.toLocaleString()} row{data.length !== 1 ? "s" : ""}
            <span className="text-muted-foreground/40 mx-1">·</span>
            {columns.length} column{columns.length !== 1 ? "s" : ""}
          </span>
        </div>
        <button
          onClick={handleCopy}
          aria-label="Copy as CSV"
          className={cn(
            "flex items-center gap-1.5 rounded-md px-2 py-1 text-[11px] font-medium transition-colors duration-150",
            copied
              ? "text-[hsl(var(--success))] bg-[hsl(var(--success)/0.08)]"
              : "text-muted-foreground/60 hover:text-foreground hover:bg-muted/50"
          )}
        >
          {copied ? (
            <Check className="h-3 w-3" aria-hidden="true" />
          ) : (
            <Copy className="h-3 w-3" aria-hidden="true" />
          )}
          {copied ? "Copied" : "Copy CSV"}
        </button>
      </div>

      {/* ── Table ─────────────────────────────────────────────────── */}
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-xs" aria-label="Query results">
          <thead>
            <tr className="border-b border-border/40 bg-muted/10">
              {columns.map((col) => {
                const firstVal = data[0][col];
                return (
                  <th
                    key={col}
                    scope="col"
                    className={cn(
                      "px-4 py-2.5 text-[11px] font-semibold text-muted-foreground uppercase tracking-wide whitespace-nowrap",
                      isNumeric(firstVal) ? "text-right" : "text-left"
                    )}
                  >
                    {col}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((row, i) => (
              <tr
                key={i}
                className="border-b border-border/20 last:border-0 hover:bg-muted/20 transition-colors duration-100"
              >
                {columns.map((col) => {
                  const val = row[col];
                  return (
                    <td
                      key={col}
                      className={cn(
                        "px-4 py-2.5 font-mono text-foreground/90",
                        isNumeric(val)
                          ? "text-right tabular-nums"
                          : "text-left",
                        (val === null || val === undefined) &&
                          "italic text-muted-foreground/40"
                      )}
                    >
                      {formatCell(val)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* ── Show more ─────────────────────────────────────────────── */}
      {hasMore && (
        <div className="border-t border-border/30 bg-muted/10">
          <Button
            variant="ghost"
            size="sm"
            className="h-8 w-full rounded-none text-xs text-muted-foreground hover:text-foreground"
            onClick={() => setExpanded((v) => !v)}
          >
            {expanded ? (
              <>
                <ChevronUp className="mr-1.5 h-3 w-3" aria-hidden="true" />
                Show fewer
              </>
            ) : (
              <>
                <ChevronDown className="mr-1.5 h-3 w-3" aria-hidden="true" />
                Show all {data.length.toLocaleString()} rows
              </>
            )}
          </Button>
        </div>
      )}
    </div>
  );
}
