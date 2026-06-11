import { Skeleton } from "@/components/ui/skeleton";

/** Skeleton for the /datasets grid — 6 placeholder cards */
export function DatasetGridSkeleton() {
  return (
    <div
      className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3"
      aria-busy="true"
      aria-label="Loading datasets…"
    >
      {Array.from({ length: 6 }).map((_, i) => (
        <div
          key={i}
          className="rounded-xl border border-border/60 bg-card/60 p-5 space-y-4"
        >
          {/* Header */}
          <div className="flex items-center gap-3">
            <Skeleton className="h-9 w-9 rounded-lg shrink-0" />
            <div className="flex-1 space-y-1.5">
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-3 w-1/3" />
            </div>
            <Skeleton className="h-5 w-12 rounded-full" />
          </div>
          {/* Stats */}
          <div className="grid grid-cols-3 gap-2">
            {[0, 1, 2].map((j) => (
              <div key={j} className="rounded-lg bg-muted/40 px-3 py-2 space-y-1.5">
                <Skeleton className="h-3 w-1/2 mx-auto" />
                <Skeleton className="h-4 w-2/3 mx-auto" />
              </div>
            ))}
          </div>
          {/* Footer */}
          <Skeleton className="h-3 w-1/3 ml-auto" />
        </div>
      ))}
    </div>
  );
}

/** Skeleton for the /datasets/[id] detail page */
export function DatasetDetailSkeleton() {
  return (
    <div
      className="space-y-6"
      aria-busy="true"
      aria-label="Loading dataset…"
    >
      {/* Page header */}
      <div className="space-y-2">
        <Skeleton className="h-8 w-56" />
        <Skeleton className="h-4 w-32" />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[300px_1fr]">
        {/* Meta panel */}
        <div className="rounded-xl border border-border/60 bg-card/60 p-5 space-y-4">
          <Skeleton className="h-5 w-24" />
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="flex items-center justify-between">
              <Skeleton className="h-3 w-20" />
              <Skeleton className="h-3 w-16" />
            </div>
          ))}
          <Skeleton className="h-px w-full" />
          <div className="flex flex-wrap gap-1.5">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-5 rounded-full" style={{ width: `${48 + i * 8}px` }} />
            ))}
          </div>
          <Skeleton className="h-px w-full" />
          <div className="space-y-2">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-9 w-full rounded-md" />
            ))}
          </div>
        </div>

        {/* Preview table */}
        <div className="rounded-xl border border-border/60 bg-card/60 overflow-hidden">
          <div className="px-5 py-4 border-b border-border/60">
            <Skeleton className="h-5 w-36" />
          </div>
          <div className="p-4 space-y-2">
            <div className="grid grid-cols-4 gap-3">
              {[0, 1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-4" />
              ))}
            </div>
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="grid grid-cols-4 gap-3">
                {[0, 1, 2, 3].map((j) => (
                  <Skeleton key={j} className="h-3.5" animate={i < 4} />
                ))}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
