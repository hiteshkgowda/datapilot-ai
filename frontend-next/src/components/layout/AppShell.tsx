import { cn } from "@/lib/utils";
import { EphemeralBanner } from "./EphemeralBanner";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { CommandPalette } from "./CommandPalette";

interface AppShellProps {
  children: React.ReactNode;
  /** Override the <main> element's className (e.g. for chat workspaces that need overflow-hidden). */
  mainClassName?: string;
}

export function AppShell({ children, mainClassName }: AppShellProps) {
  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Fixed left sidebar */}
      <Sidebar />

      {/* Right column: topbar + content */}
      <div className="flex flex-1 flex-col min-w-0 overflow-hidden">
        <Topbar />
        <EphemeralBanner />
        <main
          className={cn("flex-1 overflow-y-auto p-6", mainClassName)}
          id="main-content"
          role="main"
        >
          {children}
        </main>
      </div>

      {/* Global command palette — rendered above everything */}
      <CommandPalette />
    </div>
  );
}
