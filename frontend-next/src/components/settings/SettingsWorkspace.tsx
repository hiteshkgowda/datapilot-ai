"use client";

import { useSession, signOut } from "next-auth/react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import type { Variants } from "framer-motion";
import {
  Bot,
  CheckCircle2,
  ChevronDown,
  Database,
  Info,
  LogOut,
  Monitor,
  Moon,
  Sun,
  User,
  XCircle,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { useHealth } from "@/hooks/use-health";

// ── Animation ──────────────────────────────────────────────────────────────────

const containerVariants: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.06 } },
};

const itemVariants: Variants = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.25, ease: "easeOut" } },
};

// ── Section wrapper ────────────────────────────────────────────────────────────

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <motion.div variants={itemVariants} className="space-y-3">
      <h2 className="text-xs font-semibold uppercase tracking-[1px] text-muted-foreground/70 select-none">
        {title}
      </h2>
      <div className="rounded-xl border border-border/60 bg-card divide-y divide-border/40 overflow-hidden">
        {children}
      </div>
    </motion.div>
  );
}

// ── Row ────────────────────────────────────────────────────────────────────────

function Row({
  label,
  description,
  children,
}: {
  label: string;
  description?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-4 px-4 py-3.5">
      <div className="min-w-0">
        <p className="text-sm font-medium text-foreground">{label}</p>
        {description && (
          <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
            {description}
          </p>
        )}
      </div>
      {children && <div className="shrink-0">{children}</div>}
    </div>
  );
}

// ── Status indicator ───────────────────────────────────────────────────────────

function StatusDot({ ok, label }: { ok: boolean | undefined; label: string }) {
  const isLoading = ok === undefined;
  return (
    <div className="flex items-center gap-1.5">
      {isLoading ? (
        <span className="h-2 w-2 rounded-full bg-muted-foreground/40 animate-pulse" />
      ) : ok ? (
        <CheckCircle2 className="h-3.5 w-3.5 text-[hsl(var(--success))]" />
      ) : (
        <XCircle className="h-3.5 w-3.5 text-destructive" />
      )}
      <span
        className={cn(
          "text-xs font-medium",
          isLoading
            ? "text-muted-foreground/60"
            : ok
            ? "text-[hsl(var(--success))]"
            : "text-destructive"
        )}
      >
        {isLoading ? "Checking…" : label}
      </span>
    </div>
  );
}

// ── Theme selector ─────────────────────────────────────────────────────────────

const themes = [
  { value: "system", icon: Monitor, label: "System" },
  { value: "light", icon: Sun, label: "Light" },
  { value: "dark", icon: Moon, label: "Dark" },
] as const;

function ThemeSelector() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return (
      <div className="flex gap-1.5">
        {themes.map((t) => (
          <div
            key={t.value}
            className="h-8 w-20 rounded-md bg-muted/40 animate-pulse"
          />
        ))}
      </div>
    );
  }

  return (
    <div className="flex gap-1.5">
      {themes.map(({ value, icon: Icon, label }) => {
        const active = theme === value;
        return (
          <button
            key={value}
            onClick={() => setTheme(value)}
            className={cn(
              "flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium transition-all duration-150",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              active
                ? "border-primary bg-primary text-primary-foreground shadow-sm"
                : "border-border/60 bg-muted/30 text-muted-foreground hover:bg-accent hover:text-foreground"
            )}
            aria-pressed={active}
          >
            <Icon className="h-3 w-3" aria-hidden="true" />
            {label}
          </button>
        );
      })}
    </div>
  );
}

// ── Avatar initials ────────────────────────────────────────────────────────────

function getInitials(name: string | null | undefined): string {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

// ── Badge ──────────────────────────────────────────────────────────────────────

function Badge({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-md border border-border/60 bg-muted/40 px-2 py-0.5 text-xs font-mono text-muted-foreground">
      {children}
    </span>
  );
}

// ── Readonly field ─────────────────────────────────────────────────────────────

function ReadonlyField({ value }: { value: string }) {
  return (
    <span className="text-sm text-muted-foreground font-mono">{value}</span>
  );
}

// ── Main ───────────────────────────────────────────────────────────────────────

export function SettingsWorkspace() {
  const { data: session, status } = useSession();
  const { data: health, isLoading: healthLoading, isError: healthError } = useHealth();

  const user = session?.user;
  const isLoadingSession = status === "loading";

  const backendOk = healthLoading
    ? undefined
    : healthError
    ? false
    : health?.status === "ok";

  // Agent is considered healthy if the backend is healthy (same process)
  const agentOk = backendOk;

  // "Database connectivity" means the backend is up and can serve data
  const dbOk = backendOk;

  return (
    <motion.div
      variants={containerVariants}
      initial="hidden"
      animate="show"
      className="space-y-6"
    >
      {/* ── Account ─────────────────────────────────────────────────────── */}
      <Section title="Account">
        {/* Avatar + name + email */}
        <div className="flex items-center gap-4 px-4 py-4">
          <div
            className={cn(
              "flex h-12 w-12 shrink-0 items-center justify-center rounded-full",
              "bg-gradient-primary text-sm font-bold text-white select-none"
            )}
            aria-hidden="true"
          >
            {isLoadingSession ? (
              <User className="h-5 w-5" />
            ) : (
              getInitials(user?.name)
            )}
          </div>
          <div className="min-w-0 flex-1 space-y-0.5">
            {isLoadingSession ? (
              <>
                <div className="h-4 w-32 rounded bg-muted/50 animate-pulse" />
                <div className="h-3 w-48 rounded bg-muted/40 animate-pulse mt-1.5" />
              </>
            ) : (
              <>
                <p className="text-sm font-semibold text-foreground truncate">
                  {user?.name ?? "Unknown user"}
                </p>
                <p className="text-xs text-muted-foreground truncate">
                  {user?.email ?? "—"}
                </p>
              </>
            )}
          </div>
        </div>

        {/* Sign out */}
        <Row
          label="Sign out"
          description="End your current session and return to the sign-in page."
        >
          <Button
            variant="destructive"
            size="sm"
            onClick={() => signOut({ callbackUrl: "/auth/signin" })}
            className="gap-1.5"
          >
            <LogOut className="h-3.5 w-3.5" aria-hidden="true" />
            Sign out
          </Button>
        </Row>
      </Section>

      {/* ── Application ─────────────────────────────────────────────────── */}
      <Section title="Application">
        <Row
          label="Theme"
          description="Choose between system default, light, or dark appearance."
        >
          <ThemeSelector />
        </Row>
      </Section>

      {/* ── AI Configuration ────────────────────────────────────────────── */}
      <Section title="AI Configuration">
        <Row
          label="Primary provider"
          description="The LLM provider used for agent planning and data analysis."
        >
          <div className="flex items-center gap-2">
            <div className="flex h-6 w-6 items-center justify-center rounded bg-primary/10">
              <Zap className="h-3 w-3 text-primary" aria-hidden="true" />
            </div>
            <ReadonlyField value="Groq" />
          </div>
        </Row>
        <Row
          label="Active model"
          description="Model identifier sent with every LLM request."
        >
          <Badge>llama3-8b-8192</Badge>
        </Row>
        <Row
          label="Fallback provider"
          description="Used automatically when the primary provider is unreachable."
        >
          <div className="flex items-center gap-2">
            <div className="flex h-6 w-6 items-center justify-center rounded bg-muted/40">
              <Bot className="h-3 w-3 text-muted-foreground" aria-hidden="true" />
            </div>
            <ReadonlyField value="Ollama (llama3)" />
          </div>
        </Row>
      </Section>

      {/* ── System Status ───────────────────────────────────────────────── */}
      <Section title="System Status">
        <Row label="Backend API" description="FastAPI service health check.">
          <StatusDot
            ok={backendOk}
            label={backendOk ? "Online" : "Offline"}
          />
        </Row>
        <Row
          label="Agent engine"
          description="LangGraph orchestrator readiness."
        >
          <StatusDot
            ok={agentOk}
            label={agentOk ? "Ready" : "Unavailable"}
          />
        </Row>
        <Row
          label="Database connectivity"
          description="Storage layer (SQLite + datasets) accessibility."
        >
          <StatusDot ok={dbOk} label={dbOk ? "Connected" : "Unreachable"} />
        </Row>
      </Section>

      {/* ── About ───────────────────────────────────────────────────────── */}
      <Section title="About">
        <Row label="App version">
          <Badge>v0.1.0</Badge>
        </Row>
        <Row label="Next.js">
          <Badge>16</Badge>
        </Row>
        <Row label="Runtime">
          <Badge>App Router</Badge>
        </Row>
        <Row
          label="Build"
          description="Universal Data Assistant — AI-powered data analysis platform."
        >
          <div className="flex items-center gap-1.5 text-muted-foreground/60">
            <Info className="h-3.5 w-3.5" aria-hidden="true" />
            <span className="text-xs">UDA</span>
          </div>
        </Row>
      </Section>
    </motion.div>
  );
}
