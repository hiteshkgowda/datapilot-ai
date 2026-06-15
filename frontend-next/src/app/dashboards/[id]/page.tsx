import type { Metadata } from "next";
import { AppShell } from "@/components/layout/AppShell";
import { DashboardBuilder } from "@/components/dashboard/DashboardBuilder";

export const metadata: Metadata = { title: "Dashboard" };

interface Props {
  params: Promise<{ id: string }>;
}

export default async function SavedDashboardPage({ params }: Props) {
  const { id } = await params;

  return (
    <AppShell mainClassName="overflow-hidden p-0">
      <DashboardBuilder dashboardId={id} />
    </AppShell>
  );
}
