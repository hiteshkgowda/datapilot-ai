import type { Metadata } from "next";
import { AppShell } from "@/components/layout/AppShell";
import { CrudWorkspace } from "@/components/crud/CrudWorkspace";

export const metadata: Metadata = { title: "CRUD Workspace" };

export default function CrudPage() {
  return (
    <AppShell mainClassName="overflow-hidden p-0">
      <CrudWorkspace />
    </AppShell>
  );
}
