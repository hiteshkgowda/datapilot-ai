"use client";

import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { Bell, Moon, Search, Sun } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { useHealth } from "@/hooks/use-health";
import { useCommandPalette } from "@/providers/CommandPaletteProvider";

// ── Page title map ────────────────────────────────────────────────────────────

function getPageTitle(pathname: string): string {
  if (pathname === "/") return "Dashboard";
  if (pathname === "/datasets") return "Datasets";
  if (pathname === "/reports") return "Reports";
  if (pathname === "/crud") return "CRUD Workspace";
  if (pathname === "/agent") return "Agent";
  if (pathname === "/connections") return "Databases";
  if (pathname === "/settings") return "Settings";
  if (pathname.includes("/ask")) return "Analytics";
  if (pathname.includes("/forecast")) return "Forecasting";
  if (pathname.startsWith("/datasets/") && pathname.endsWith("/reports")) return "Reports";
  if (pathname.startsWith("/datasets/")) return "Dataset";
  return "Universal Data Assistant";
}

// ── Sub-components ────────────────────────────────────────────────────────────

function SystemStatus() {
  const { data, isError, isPending } = useHealth();

  if (isPending) {
    return (
      <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground/60">
        <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/40 animate-pulse-status" />
        <span className="hidden sm:inline">Connecting</span>
      </span>
    );
  }

  if (isError || data?.status !== "ok") {
    return (
      <span
        className="flex items-center gap-1.5 text-[11px] text-destructive/80"
        role="status"
        aria-label="Backend offline"
      >
        <span className="h-1.5 w-1.5 rounded-full status-dot-offline" />
        <span className="hidden sm:inline">Offline</span>
      </span>
    );
  }

  return (
    <span
      className="flex items-center gap-1.5 text-[11px] text-muted-foreground/60"
      role="status"
      aria-label="Backend connected"
    >
      <span className="h-1.5 w-1.5 rounded-full status-dot-online" />
      <span className="hidden sm:inline">Connected</span>
    </span>
  );
}

function SearchTrigger() {
  const { setOpen } = useCommandPalette();

  return (
    <button
      onClick={() => setOpen(true)}
      className={cn(
        "flex items-center gap-2 rounded-lg border border-border/70",
        "bg-muted/30 px-3 py-1.5",
        "text-sm text-muted-foreground/70",
        "hover:bg-muted/60 hover:text-muted-foreground hover:border-border",
        "transition-all duration-150",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        "w-48 xl:w-64"
      )}
      aria-label="Open command palette"
    >
      <Search className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      <span className="flex-1 text-left text-xs">Search…</span>
      <kbd
        className={cn(
          "hidden sm:inline-flex items-center gap-0.5 rounded border border-border",
          "px-1 py-0.5 text-[10px] font-medium text-muted-foreground/50"
        )}
      >
        ⌘K
      </kbd>
    </button>
  );
}

function ThemeToggle() {
  const { theme, setTheme } = useTheme();

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
      aria-label="Toggle theme"
      className="h-8 w-8 text-muted-foreground hover:text-foreground"
    >
      <Sun className="h-4 w-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
      <Moon className="absolute h-4 w-4 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
    </Button>
  );
}

function NotificationButton() {
  return (
    <Button
      variant="ghost"
      size="icon"
      className="h-8 w-8 text-muted-foreground hover:text-foreground relative"
      aria-label="Notifications"
    >
      <Bell className="h-4 w-4" />
    </Button>
  );
}

function UserAvatar() {
  return (
    <button
      className={cn(
        "flex h-7 w-7 items-center justify-center rounded-full",
        "bg-primary/20 text-[11px] font-semibold text-primary",
        "hover:bg-primary/30 transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      )}
      aria-label="User menu"
    >
      HK
    </button>
  );
}

// ── Topbar ────────────────────────────────────────────────────────────────────

export function Topbar() {
  const pathname = usePathname();
  const title = getPageTitle(pathname);

  return (
    <header
      className={cn(
        "flex h-12 shrink-0 items-center justify-between",
        "border-b border-border/50 bg-background/75",
        "backdrop-blur-[12px] px-4 gap-4"
      )}
      role="banner"
    >
      {/* Left: page title — Playfair Display matching QF topbar */}
      <h1 className="text-base font-semibold text-foreground shrink-0 font-display tracking-tight">
        {title}
      </h1>

      {/* Center: search */}
      <div className="flex-1 flex justify-center">
        <SearchTrigger />
      </div>

      {/* Right: actions */}
      <div className="flex items-center gap-1 shrink-0">
        <SystemStatus />
        <div className="w-px h-4 bg-border/60 mx-1" aria-hidden="true" />
        <NotificationButton />
        <ThemeToggle />
        <div className="w-px h-4 bg-border/60 mx-1" aria-hidden="true" />
        <UserAvatar />
      </div>
    </header>
  );
}
