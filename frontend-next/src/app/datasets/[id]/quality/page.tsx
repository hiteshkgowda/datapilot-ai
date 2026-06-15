import type { Metadata } from "next";
import { AppShell } from "@/components/layout/AppShell";
import { DataQualityDashboard } from "@/components/quality/DataQualityDashboard";

export const metadata: Metadata = { title: "Data Quality" };

interface Props {
  params: Promise<{ id: string }>;
}

export default async function DataQualityPage({ params }: Props) {
  const { id } = await params;

  return (
    <AppShell>
      <DataQualityDashboard datasetId={id} />
    </AppShell>
  );
}
