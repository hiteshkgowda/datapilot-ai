"use client";

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { formatDtype, isNumericDtype } from "@/lib/format";
import type { DatasetPreview } from "@/lib/api/types";

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") {
    return Number.isInteger(value) ? value.toLocaleString() : value.toPrecision(6);
  }
  const str = String(value);
  return str.length > 60 ? str.slice(0, 57) + "…" : str;
}

interface PreviewTableProps {
  preview: DatasetPreview;
}

export function PreviewTable({ preview }: PreviewTableProps) {
  const { column_names, data_types, preview_rows, preview_row_count, rows } =
    preview;

  return (
    <div className="rounded-xl border border-border/60 bg-card/60 backdrop-blur-sm overflow-hidden">
      {/* Panel header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-border/60">
        <div>
          <h2 className="text-sm font-semibold text-foreground">Preview</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Showing {preview_row_count} of {rows.toLocaleString()} rows ·{" "}
            {column_names.length} columns
          </p>
        </div>
      </div>

      {/* Scrollable table */}
      <div className="overflow-x-auto">
        <table
          className="w-full text-xs border-collapse"
          aria-label={`Preview of ${preview.filename}`}
        >
          <thead>
            <tr className="border-b border-border/60 bg-muted/30">
              {/* Row number gutter */}
              <th
                className="w-10 py-3 pl-4 pr-2 text-right text-muted-foreground/50 font-normal select-none"
                aria-hidden="true"
              >
                #
              </th>
              {column_names.map((col) => {
                const dtype = data_types[col] ?? "object";
                const isNum = isNumericDtype(dtype);
                return (
                  <th
                    key={col}
                    scope="col"
                    className={cn(
                      "px-4 py-3 font-medium text-foreground text-left whitespace-nowrap",
                      isNum && "text-right"
                    )}
                  >
                    <div
                      className={cn(
                        "flex flex-col gap-0.5",
                        isNum && "items-end"
                      )}
                    >
                      <span>{col}</span>
                      <Badge variant="muted" className="text-[10px] px-1.5 py-0">
                        {formatDtype(dtype)}
                      </Badge>
                    </div>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {preview_rows.map((row, i) => (
              <tr
                key={i}
                className={cn(
                  "border-b border-border/40 transition-colors",
                  "hover:bg-muted/20"
                )}
              >
                {/* Row number */}
                <td
                  className="py-2.5 pl-4 pr-2 text-right text-muted-foreground/40 font-mono select-none"
                  aria-hidden="true"
                >
                  {i + 1}
                </td>
                {column_names.map((col) => {
                  const dtype = data_types[col] ?? "object";
                  const isNum = isNumericDtype(dtype);
                  const raw = row[col];
                  const isNull = raw === null || raw === undefined;
                  return (
                    <td
                      key={col}
                      className={cn(
                        "px-4 py-2.5 font-mono",
                        isNum ? "text-right" : "text-left",
                        isNull && "text-muted-foreground/40 italic"
                      )}
                    >
                      {formatCell(raw)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>

        {preview_rows.length === 0 && (
          <p className="py-8 text-center text-sm text-muted-foreground">
            No rows to preview.
          </p>
        )}
      </div>
    </div>
  );
}
