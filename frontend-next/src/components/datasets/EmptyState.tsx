import { Database } from "lucide-react";

export function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border/60 py-16 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-full bg-muted/50">
        <Database className="h-6 w-6 text-muted-foreground" aria-hidden="true" />
      </div>
      <h3 className="mt-4 text-sm font-semibold text-foreground">No datasets yet</h3>
      <p className="mt-1.5 max-w-xs text-sm text-muted-foreground">
        Upload a CSV or Excel file above to get started. Database tables can be
        added from the Connections workspace.
      </p>
    </div>
  );
}
