import type { Metadata } from "next";
import { AppShell } from "@/components/layout/AppShell";
import { DashboardHub } from "@/components/dashboard/DashboardHub";

export const metadata: Metadata = { title: "Dashboards" };

export default function DashboardsPage() {
  return (
    <AppShell>
      <DashboardHub />
    </AppShell>
  );
}
