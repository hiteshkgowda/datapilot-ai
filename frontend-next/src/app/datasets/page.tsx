import type { Metadata } from "next";
import { AppShell } from "@/components/layout/AppShell";
import { DatasetsDashboard } from "@/components/datasets/DatasetsDashboard";

export const metadata: Metadata = { title: "Datasets" };

export default function DatasetsPage() {
  return (
    <AppShell>
      <div className="max-w-6xl mx-auto space-y-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Datasets</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Upload files or browse connected database tables.
          </p>
        </div>
        <DatasetsDashboard />
      </div>
    </AppShell>
  );
}
