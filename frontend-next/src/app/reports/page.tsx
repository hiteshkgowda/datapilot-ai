import type { Metadata } from "next";
import { AppShell } from "@/components/layout/AppShell";
import { ReportsWorkspace } from "@/components/reports/ReportsWorkspace";

export const metadata: Metadata = { title: "Reports" };

export default function ReportsPage() {
  return (
    <AppShell>
      <ReportsWorkspace />
    </AppShell>
  );
}
