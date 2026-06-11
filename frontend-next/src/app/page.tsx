import type { Metadata } from "next";
import { AppShell } from "@/components/layout/AppShell";
import { Dashboard } from "@/components/dashboard/Dashboard";

export const metadata: Metadata = { title: "Dashboard" };

export default function HomePage() {
  return (
    <AppShell>
      <Dashboard />
    </AppShell>
  );
}
