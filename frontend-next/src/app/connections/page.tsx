import type { Metadata } from "next";
import { AppShell } from "@/components/layout/AppShell";
import { ConnectionsWorkspace } from "@/components/connections/ConnectionsWorkspace";

export const metadata: Metadata = { title: "Connections" };

export default function ConnectionsPage() {
  return (
    <AppShell>
      <ConnectionsWorkspace />
    </AppShell>
  );
}
