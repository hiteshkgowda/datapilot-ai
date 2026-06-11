"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import type { Variants } from "framer-motion";
import {
  Bot,
  Database,
  FileText,
  LayoutDashboard,
  Link2,
  PenLine,
  Search,
  Settings,
  Upload,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useCommandPalette } from "@/providers/CommandPaletteProvider";

interface CommandItem {
  id: string;
  label: string;
  description?: string;
  href: string;
  icon: React.ElementType;
  section: string;
  keywords: string[];
}

const ITEMS: CommandItem[] = [
  {
    id: "dashboard",
    label: "Dashboard",
    description: "Overview and recent activity",
    href: "/",
    icon: LayoutDashboard,
    section: "Navigate",
    keywords: ["home", "overview"],
  },
  {
    id: "datasets",
    label: "Datasets",
    description: "Upload and manage datasets",
    href: "/datasets",
    icon: Database,
    section: "Navigate",
    keywords: ["upload", "csv", "excel", "data"],
  },
  {
    id: "reports",
    label: "Reports",
    description: "Generate and download PDF reports",
    href: "/reports",
    icon: FileText,
    section: "Navigate",
    keywords: ["pdf", "generate", "export"],
  },
  {
    id: "crud",
    label: "CRUD Workspace",
    description: "Create, update, delete database rows",
    href: "/crud",
    icon: PenLine,
    section: "Navigate",
    keywords: ["create", "update", "delete", "write", "edit"],
  },
  {
    id: "agent",
    label: "Agent",
    description: "Run multi-step AI workflows",
    href: "/agent",
    icon: Bot,
    section: "Navigate",
    keywords: ["ai", "workflow", "multi-step", "automate"],
  },
  {
    id: "databases",
    label: "Databases",
    description: "Manage database connections",
    href: "/connections",
    icon: Link2,
    section: "Navigate",
    keywords: ["connect", "sql", "postgres", "sqlite", "mysql"],
  },
  {
    id: "settings",
    label: "Settings",
    description: "Application settings",
    href: "/settings",
    icon: Settings,
    section: "Navigate",
    keywords: ["preferences", "config"],
  },
  {
    id: "upload",
    label: "Upload Dataset",
    description: "Add a CSV or Excel file",
    href: "/datasets",
    icon: Upload,
    section: "Quick Actions",
    keywords: ["import", "file", "new"],
  },
];

const backdropVariants: Variants = {
  hidden: { opacity: 0 },
  show: { opacity: 1 },
  exit: { opacity: 0 },
};

const panelVariants: Variants = {
  hidden: { opacity: 0, scale: 0.97, y: -8 },
  show: {
    opacity: 1,
    scale: 1,
    y: 0,
    transition: { type: "spring", stiffness: 500, damping: 36 },
  },
  exit: { opacity: 0, scale: 0.97, y: -4, transition: { duration: 0.12 } },
};

export function CommandPalette() {
  const { open, setOpen } = useCommandPalette();
  const [query, setQuery] = useState("");
  const [activeIdx, setActiveIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const router = useRouter();

  // Filter items
  const q = query.toLowerCase().trim();
  const filtered = q
    ? ITEMS.filter(
        (item) =>
          item.label.toLowerCase().includes(q) ||
          (item.description?.toLowerCase().includes(q)) ||
          item.keywords.some((k) => k.includes(q))
      )
    : ITEMS;

  // Reset state when opened
  useEffect(() => {
    if (open) {
      setQuery("");
      setActiveIdx(0);
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [open]);

  // Keyboard navigation
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIdx((i) => Math.min(i + 1, filtered.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIdx((i) => Math.max(i - 1, 0));
      } else if (e.key === "Enter") {
        e.preventDefault();
        const item = filtered[activeIdx];
        if (item) navigate(item.href);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, filtered, activeIdx]); // eslint-disable-line react-hooks/exhaustive-deps

  // Scroll active item into view
  useEffect(() => {
    const el = listRef.current?.children[activeIdx] as HTMLElement | undefined;
    el?.scrollIntoView({ block: "nearest" });
  }, [activeIdx]);

  // Reset active index when query changes
  useEffect(() => {
    setActiveIdx(0);
  }, [query]);

  function navigate(href: string) {
    setOpen(false);
    router.push(href);
  }

  // Group filtered items by section
  const sections = filtered.reduce<Record<string, CommandItem[]>>((acc, item) => {
    (acc[item.section] ??= []).push(item);
    return acc;
  }, {});

  // Flat index map for keyboard nav
  const flatItems = filtered;

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          variants={backdropVariants}
          initial="hidden"
          animate="show"
          exit="exit"
          transition={{ duration: 0.15 }}
          className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh]"
          style={{
            background: "hsl(var(--background) / 0.6)",
            backdropFilter: "blur(8px) saturate(1.2)",
          }}
          onClick={() => setOpen(false)}
          aria-modal="true"
          role="dialog"
          aria-label="Command palette"
        >
          <motion.div
            variants={panelVariants}
            initial="hidden"
            animate="show"
            exit="exit"
            className={cn(
              "w-full max-w-[560px] mx-4 overflow-hidden",
              "rounded-xl border border-border bg-elevated",
              "elevation-lg"
            )}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Search input */}
            <div className="flex items-center gap-3 border-b border-border px-4 py-3.5">
              <Search className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search pages, actions…"
                className={cn(
                  "flex-1 bg-transparent text-sm text-foreground",
                  "placeholder:text-muted-foreground/60",
                  "focus:outline-none"
                )}
                aria-label="Command search"
              />
              <kbd
                className={cn(
                  "hidden sm:inline-flex items-center gap-0.5 rounded border border-border",
                  "px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground"
                )}
              >
                Esc
              </kbd>
            </div>

            {/* Results */}
            <div className="max-h-[380px] overflow-y-auto py-2">
              {flatItems.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-10 gap-2">
                  <Search className="h-8 w-8 text-muted-foreground/20" />
                  <p className="text-sm text-muted-foreground">No results for "{query}"</p>
                </div>
              ) : (
                <ul ref={listRef} role="listbox">
                  {Object.entries(sections).map(([section, items]) => (
                    <li key={section} role="presentation">
                      <div className="px-4 pb-1 pt-2">
                        <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/60">
                          {section}
                        </p>
                      </div>
                      <ul>
                        {items.map((item) => {
                          const idx = flatItems.indexOf(item);
                          const isActive = idx === activeIdx;
                          return (
                            <li key={item.id} role="option" aria-selected={isActive}>
                              <button
                                className={cn(
                                  "w-full flex items-center gap-3 px-4 py-2.5 text-left",
                                  "transition-colors duration-100",
                                  isActive
                                    ? "bg-primary/10 text-foreground"
                                    : "text-foreground/80 hover:bg-muted/50"
                                )}
                                onMouseEnter={() => setActiveIdx(idx)}
                                onClick={() => navigate(item.href)}
                              >
                                <div
                                  className={cn(
                                    "flex h-7 w-7 shrink-0 items-center justify-center rounded-lg",
                                    isActive ? "bg-primary/15" : "bg-muted/60"
                                  )}
                                >
                                  <item.icon
                                    className={cn(
                                      "h-3.5 w-3.5",
                                      isActive ? "text-primary" : "text-muted-foreground"
                                    )}
                                  />
                                </div>
                                <div className="flex-1 min-w-0">
                                  <p className="text-sm font-medium truncate">{item.label}</p>
                                  {item.description && (
                                    <p className="text-xs text-muted-foreground truncate">
                                      {item.description}
                                    </p>
                                  )}
                                </div>
                                {isActive && (
                                  <kbd className="shrink-0 hidden sm:inline-flex items-center gap-0.5 rounded border border-border px-1.5 py-0.5 text-[10px] text-muted-foreground">
                                    ↵
                                  </kbd>
                                )}
                              </button>
                            </li>
                          );
                        })}
                      </ul>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {/* Footer */}
            <div className="flex items-center justify-between border-t border-border px-4 py-2">
              <div className="flex items-center gap-3 text-[10px] text-muted-foreground/60">
                <span className="flex items-center gap-1">
                  <kbd className="rounded border border-border px-1 py-0.5">↑↓</kbd>
                  navigate
                </span>
                <span className="flex items-center gap-1">
                  <kbd className="rounded border border-border px-1 py-0.5">↵</kbd>
                  select
                </span>
              </div>
              <span className="text-[10px] text-muted-foreground/40">
                {flatItems.length} results
              </span>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
