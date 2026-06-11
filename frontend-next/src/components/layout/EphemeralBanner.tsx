"use client";

import { AlertTriangle, X } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { useHealth } from "@/hooks/use-health";

export function EphemeralBanner() {
  const { data } = useHealth();
  const [dismissed, setDismissed] = useState(false);

  if (!data?.storage?.ephemeral || dismissed) return null;

  return (
    <div
      role="alert"
      className={cn(
        "flex items-center gap-2.5 px-4 py-2 shrink-0",
        "bg-warning/10 border-b border-warning/25 text-warning",
      )}
    >
      <AlertTriangle className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      <p className="flex-1 text-xs font-medium leading-none">
        Running on free-tier infrastructure. Uploaded data may be reset between
        deploys.
      </p>
      <button
        onClick={() => setDismissed(true)}
        className="shrink-0 rounded p-0.5 hover:bg-warning/20 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-label="Dismiss warning"
      >
        <X className="h-3 w-3" aria-hidden="true" />
      </button>
    </div>
  );
}
