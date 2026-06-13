import type { Metadata } from "next";
import { AppShell } from "@/components/layout/AppShell";
import { AnomalyWorkspace } from "@/components/anomalies/AnomalyWorkspace";

export const metadata: Metadata = { title: "Anomaly Detection" };

interface Props {
  params: Promise<{ id: string }>;
}

export default async function AnomalyDetectionPage({ params }: Props) {
  const { id } = await params;

  return (
    <AppShell mainClassName="overflow-hidden p-0">
      <AnomalyWorkspace datasetId={id} />
    </AppShell>
  );
}
