"use client";

import { useRouter } from "next/navigation";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { useDatasets } from "@/hooks/use-datasets";

interface DatasetSelectorProps {
  currentId: string;
}

export function DatasetSelector({ currentId }: DatasetSelectorProps) {
  const router = useRouter();
  const { data } = useDatasets();

  const datasets = data?.datasets ?? [];
  const current = datasets.find((d) => d.id === currentId);

  function handleChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const newId = e.target.value;
    if (newId && newId !== currentId) {
      router.push(`/datasets/${newId}/ask`);
    }
  }

  const label = current?.filename ?? "Dataset";
  const canSwitch = datasets.length > 1;

  return (
    <div
      className={cn(
        "relative inline-flex items-center gap-1.5 rounded-md px-2 py-1",
        canSwitch &&
          "hover:bg-muted/50 transition-colors duration-150 cursor-pointer"
      )}
    >
      <span
        className="text-sm font-semibold text-foreground leading-none truncate max-w-[200px]"
        title={label}
      >
        {label}
      </span>
      {canSwitch && (
        <ChevronDown
          className="h-3.5 w-3.5 text-muted-foreground/60 shrink-0"
          aria-hidden="true"
        />
      )}
      {canSwitch && (
        <select
          value={currentId}
          onChange={handleChange}
          className="absolute inset-0 w-full cursor-pointer opacity-0"
          aria-label="Switch dataset"
        >
          {datasets.map((ds) => (
            <option key={ds.id} value={ds.id}>
              {ds.filename}
            </option>
          ))}
        </select>
      )}
    </div>
  );
}
