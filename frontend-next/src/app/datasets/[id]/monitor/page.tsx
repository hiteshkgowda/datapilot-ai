import type { Metadata } from "next";
import { AppShell } from "@/components/layout/AppShell";
import { KPIMonitorDashboard } from "@/components/monitor/KPIMonitorDashboard";

export const metadata: Metadata = { title: "KPI Monitor" };

interface Props {
  params: Promise<{ id: string }>;
}

export default async function KPIMonitorPage({ params }: Props) {
  const { id } = await params;

  return (
    <AppShell>
      <KPIMonitorDashboard datasetId={id} />
    </AppShell>
  );
}
