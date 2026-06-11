import type { Metadata } from "next";
import { AppShell } from "@/components/layout/AppShell";
import { ReportsWorkspace } from "@/components/reports/ReportsWorkspace";

export const metadata: Metadata = { title: "Generate Report" };

interface Props {
  params: Promise<{ id: string }>;
}

export default async function DatasetReportsPage({ params }: Props) {
  const { id } = await params;

  return (
    <AppShell>
      <ReportsWorkspace defaultDatasetId={id} />
    </AppShell>
  );
}
