"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, useReducedMotion } from "framer-motion";
import {
  Bot,
  ChevronLeft,
  ChevronRight,
  Database,
  FileText,
  LayoutDashboard,
  Link2,
  PenLine,
  Settings,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Tooltip, TooltipProvider } from "@/components/ui/tooltip";
import { useSidebar } from "@/hooks/use-sidebar";

interface NavItem {
  href: string;
  label: string;
  icon: React.ElementType;
  exact?: boolean;
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

const navGroups: NavGroup[] = [
  {
    label: "Workspace",
    items: [
      { href: "/", label: "Dashboard", icon: LayoutDashboard, exact: true },
      { href: "/datasets", label: "Datasets", icon: Database },
    ],
  },
  {
    label: "Analysis",
    items: [{ href: "/reports", label: "Reports", icon: FileText }],
  },
  {
    label: "Operations",
    items: [
      { href: "/crud", label: "CRUD", icon: PenLine },
      { href: "/agent", label: "Agent", icon: Bot },
    ],
  },
  {
    label: "System",
    items: [{ href: "/connections", label: "Databases", icon: Link2 }],
  },
];

const settingsItem: NavItem = { href: "/settings", label: "Settings", icon: Settings };

function NavLink({ item, collapsed }: { item: NavItem; collapsed: boolean }) {
  const pathname = usePathname();
  const isActive = item.exact
    ? pathname === item.href
    : pathname === item.href || pathname.startsWith(item.href + "/");

  const inner = (
    <Link
      href={item.href}
      aria-current={isActive ? "page" : undefined}
      className={cn(
        "group relative flex h-8 items-center gap-2.5 rounded-md text-sm transition-all duration-[300ms] cubic-bezier(0.4,0,0.2,1)",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        collapsed ? "w-8 justify-center px-0" : "px-2.5",
        isActive
          ? "bg-primary text-primary-foreground font-medium shadow-[0_4px_15px_rgba(26,92,58,0.28)]"
          : "text-sidebar-muted hover:bg-accent/60 hover:text-sidebar-foreground"
      )}
    >
      {/* Left accent bar — shown only when not full-bg active (collapsed mode) */}
      {isActive && collapsed && (
        <span
          className="absolute left-0 top-1/2 -translate-y-1/2 h-4 w-0.5 rounded-r-full bg-primary-foreground/70"
          aria-hidden="true"
        />
      )}

      <item.icon
        className={cn(
          "h-4 w-4 shrink-0 transition-colors",
          isActive ? "text-primary-foreground" : "text-sidebar-muted group-hover:text-sidebar-foreground"
        )}
        aria-hidden="true"
      />

      {!collapsed && (
        <span className="truncate leading-none">{item.label}</span>
      )}
    </Link>
  );

  if (collapsed) {
    return (
      <Tooltip content={item.label} side="right">
        {inner}
      </Tooltip>
    );
  }

  return inner;
}

function GroupLabel({ label, collapsed }: { label: string; collapsed: boolean }) {
  if (collapsed) {
    return <div className="my-1 h-px bg-sidebar-border/60 mx-2" />;
  }
  return (
    <p className="px-2.5 pb-1 pt-3 text-[10px] font-semibold uppercase tracking-[1px] text-sidebar-muted/70 select-none font-sans">
      {label}
    </p>
  );
}

export function Sidebar() {
  const { collapsed, toggle, mounted } = useSidebar();
  const shouldReduceMotion = useReducedMotion();

  if (!mounted) return null;

  const width = collapsed ? 52 : 232;

  return (
    <TooltipProvider>
      <motion.aside
        initial={false}
        animate={{ width }}
        transition={
          shouldReduceMotion
            ? { duration: 0 }
            : { type: "spring", stiffness: 320, damping: 32 }
        }
        className={cn(
          "relative flex h-screen flex-col shrink-0 overflow-hidden",
          "bg-sidebar border-r border-sidebar-border"
        )}
        aria-label="Main navigation"
      >
        {/* ── Logo ─────────────────────────────────────────────────── */}
        <div
          className={cn(
            "flex h-12 shrink-0 items-center border-b border-sidebar-border",
            collapsed ? "justify-center px-0" : "gap-2.5 px-3.5"
          )}
        >
          <div
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-gradient-primary"
            aria-hidden="true"
          >
            <Zap className="h-3.5 w-3.5 text-white" />
          </div>
          {!collapsed && (
            <div className="min-w-0">
              <p className="text-sm font-semibold tracking-tight truncate text-sidebar-foreground leading-none">
                Data Assistant
              </p>
              <p className="text-[10px] text-sidebar-muted leading-none mt-0.5">
                Universal
              </p>
            </div>
          )}
        </div>

        {/* ── Navigation ───────────────────────────────────────────── */}
        <nav
          className="flex flex-1 flex-col overflow-y-auto overflow-x-hidden py-2 px-1.5 gap-0"
          aria-label="Primary navigation"
        >
          {navGroups.map((group) => (
            <div key={group.label}>
              <GroupLabel label={group.label} collapsed={collapsed} />
              <div className="space-y-0.5">
                {group.items.map((item) => (
                  <NavLink key={item.href} item={item} collapsed={collapsed} />
                ))}
              </div>
            </div>
          ))}

          {/* Settings pushed to bottom */}
          <div className="mt-auto pt-2">
            <div className="my-1 h-px bg-sidebar-border/60" />
            <NavLink item={settingsItem} collapsed={collapsed} />
          </div>
        </nav>

        {/* ── User area ────────────────────────────────────────────── */}
        {!collapsed && (
          <div className="shrink-0 border-t border-sidebar-border px-3.5 py-2.5 sidebar-profile">
            <div className="flex items-center gap-2.5">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-primary text-xs font-bold text-white">
                HK
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-xs font-semibold text-sidebar-foreground truncate leading-none">
                  Hitesh K
                </p>
                <p className="text-[10px] text-primary truncate mt-0.5">
                  hiteshkgowda56@gmail.com
                </p>
              </div>
            </div>
          </div>
        )}

        {/* ── Collapse toggle ───────────────────────────────────────── */}
        <button
          onClick={toggle}
          className={cn(
            "absolute -right-3 top-[44px] z-10",
            "flex h-5.5 w-5.5 items-center justify-center",
            "rounded-full border border-sidebar-border bg-sidebar elevation-sm",
            "text-sidebar-muted hover:text-sidebar-foreground hover:bg-muted/50",
            "transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          )}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          style={{ height: "22px", width: "22px" }}
        >
          {collapsed ? (
            <ChevronRight className="h-2.5 w-2.5" aria-hidden="true" />
          ) : (
            <ChevronLeft className="h-2.5 w-2.5" aria-hidden="true" />
          )}
        </button>
      </motion.aside>
    </TooltipProvider>
  );
}
