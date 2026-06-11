import type { Metadata } from "next";
import { AppShell } from "@/components/layout/AppShell";
import { SettingsWorkspace } from "@/components/settings/SettingsWorkspace";

export const metadata: Metadata = { title: "Settings" };

export default function SettingsPage() {
  return (
    <AppShell>
      <div className="max-w-3xl mx-auto space-y-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Manage your account, preferences, and system configuration.
          </p>
        </div>
        <SettingsWorkspace />
      </div>
    </AppShell>
  );
}
