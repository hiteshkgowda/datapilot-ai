"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { Variants } from "framer-motion";
import {
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Database,
  Loader2,
  Server,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useCreateConnection } from "@/hooks/use-connections";
import type { ConnectionCreate, DbType } from "@/lib/api/types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface WizardState {
  db_type: DbType | "";
  name: string;
  host: string;
  port: string;
  database: string;
  username: string;
  password: string;
}

const DEFAULTS: WizardState = {
  db_type: "",
  name: "",
  host: "",
  port: "",
  database: "",
  username: "",
  password: "",
};

const DEFAULT_PORTS: Record<string, string> = {
  postgresql: "5432",
  mysql: "3306",
};

// ---------------------------------------------------------------------------
// Step indicators
// ---------------------------------------------------------------------------

const STEPS = ["Database type", "Credentials", "Review & save"];

function StepDots({ current }: { current: number }) {
  return (
    <div className="flex items-center gap-2" aria-label="Progress">
      {STEPS.map((label, i) => (
        <div key={i} className="flex items-center gap-2">
          <div
            className={cn(
              "flex h-6 w-6 items-center justify-center rounded-full text-[11px] font-semibold border transition-colors duration-200",
              i < current
                ? "bg-primary border-primary text-primary-foreground"
                : i === current
                ? "border-primary text-primary bg-primary/10"
                : "border-border/50 text-muted-foreground"
            )}
            aria-current={i === current ? "step" : undefined}
          >
            {i < current ? <CheckCircle2 className="h-3.5 w-3.5" /> : i + 1}
          </div>
          {i < STEPS.length - 1 && (
            <div
              className={cn(
                "h-px w-8 transition-colors duration-300",
                i < current ? "bg-primary" : "bg-border/40"
              )}
            />
          )}
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 1 — DB type
// ---------------------------------------------------------------------------

const DB_OPTIONS: { type: DbType; label: string; desc: string; color: string }[] = [
  {
    type: "sqlite",
    label: "SQLite",
    desc: "Local file database",
    color: "border-sky-400/30 text-sky-400 bg-sky-400/5",
  },
  {
    type: "postgresql",
    label: "PostgreSQL",
    desc: "Client–server relational DB",
    color: "border-blue-400/30 text-blue-400 bg-blue-400/5",
  },
  {
    type: "mysql",
    label: "MySQL",
    desc: "Popular open-source RDBMS",
    color: "border-orange-400/30 text-orange-400 bg-orange-400/5",
  },
];

function Step1DbType({
  state,
  onChange,
}: {
  state: WizardState;
  onChange: (s: WizardState) => void;
}) {
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Choose the type of database you want to connect to.
      </p>
      <div className="grid grid-cols-1 gap-3">
        {DB_OPTIONS.map(({ type, label, desc, color }) => (
          <button
            key={type}
            type="button"
            onClick={() =>
              onChange({
                ...state,
                db_type: type,
                port: DEFAULT_PORTS[type] ?? "",
              })
            }
            className={cn(
              "flex items-center gap-4 rounded-xl border px-4 py-3.5 text-left transition-all duration-150",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              state.db_type === type
                ? cn("border-primary/50 bg-primary/5", color)
                : "border-border/50 hover:border-border/80 hover:bg-muted/20"
            )}
          >
            <div
              className={cn(
                "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border",
                state.db_type === type ? color : "border-border/40 text-muted-foreground"
              )}
            >
              <Database className="h-4 w-4" aria-hidden="true" />
            </div>
            <div>
              <p className="text-sm font-semibold text-foreground">{label}</p>
              <p className="text-[11px] text-muted-foreground">{desc}</p>
            </div>
            {state.db_type === type && (
              <CheckCircle2 className="ml-auto h-4 w-4 text-primary shrink-0" />
            )}
          </button>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 2 — Credentials
// ---------------------------------------------------------------------------

interface FieldProps {
  label: string;
  id: string;
  type?: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  required?: boolean;
  autoComplete?: string;
}

function Field({
  label,
  id,
  type = "text",
  value,
  onChange,
  placeholder,
  required,
  autoComplete,
}: FieldProps) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="text-xs text-muted-foreground">
        {label}
        {required && <span className="text-destructive ml-0.5">*</span>}
      </label>
      <input
        id={id}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoComplete={autoComplete}
        className={cn(
          "w-full rounded-lg border border-border/50 bg-background/60 px-3 py-2",
          "text-sm text-foreground placeholder:text-muted-foreground/40",
          "focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        )}
      />
    </div>
  );
}

function Step2Credentials({
  state,
  onChange,
}: {
  state: WizardState;
  onChange: (s: WizardState) => void;
}) {
  const isSqlite = state.db_type === "sqlite";

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        {isSqlite
          ? "Enter a human-readable name and the path to the SQLite file."
          : "Enter the connection details for your database server."}
      </p>

      <Field
        label="Connection name"
        id="conn-name"
        value={state.name}
        onChange={(v) => onChange({ ...state, name: v })}
        placeholder="My Database"
        required
      />

      {isSqlite ? (
        <Field
          label="File path"
          id="conn-database"
          value={state.database}
          onChange={(v) => onChange({ ...state, database: v })}
          placeholder="/data/mydb.sqlite"
          required
        />
      ) : (
        <>
          <div className="grid grid-cols-[1fr_100px] gap-3">
            <Field
              label="Host"
              id="conn-host"
              value={state.host}
              onChange={(v) => onChange({ ...state, host: v })}
              placeholder="localhost"
              required
              autoComplete="off"
            />
            <Field
              label="Port"
              id="conn-port"
              value={state.port}
              onChange={(v) => onChange({ ...state, port: v })}
              placeholder="5432"
            />
          </div>

          <Field
            label="Database"
            id="conn-database"
            value={state.database}
            onChange={(v) => onChange({ ...state, database: v })}
            placeholder="mydb"
            required
          />

          <div className="grid grid-cols-2 gap-3">
            <Field
              label="Username"
              id="conn-username"
              value={state.username}
              onChange={(v) => onChange({ ...state, username: v })}
              placeholder="postgres"
              autoComplete="username"
            />
            <Field
              label="Password"
              id="conn-password"
              type="password"
              value={state.password}
              onChange={(v) => onChange({ ...state, password: v })}
              placeholder="••••••••"
              autoComplete="current-password"
            />
          </div>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 3 — Review & save
// ---------------------------------------------------------------------------

function ReviewRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-1.5 text-sm border-b border-border/20 last:border-0">
      <span className="text-muted-foreground text-xs">{label}</span>
      <span className="text-foreground font-mono text-xs">{value || "—"}</span>
    </div>
  );
}

function Step3Review({
  state,
  isSuccess,
}: {
  state: WizardState;
  isSuccess: boolean;
}) {
  if (isSuccess) {
    return (
      <div className="flex flex-col items-center justify-center py-6 text-center gap-3">
        <CheckCircle2 className="h-10 w-10 text-emerald-400" />
        <p className="text-sm font-semibold text-foreground">Connection saved!</p>
        <p className="text-xs text-muted-foreground">
          You can now browse its tables and register them as datasets.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Review your connection details before saving.
      </p>
      <div className="rounded-lg border border-border/40 bg-muted/10 px-4 py-2 space-y-0">
        <ReviewRow label="Name" value={state.name} />
        <ReviewRow
          label="Type"
          value={
            state.db_type === "sqlite"
              ? "SQLite"
              : state.db_type === "postgresql"
              ? "PostgreSQL"
              : state.db_type === "mysql"
              ? "MySQL"
              : "—"
          }
        />
        {state.db_type !== "sqlite" && (
          <>
            <ReviewRow
              label="Host"
              value={state.host + (state.port ? `:${state.port}` : "")}
            />
            <ReviewRow label="Database" value={state.database} />
            <ReviewRow label="Username" value={state.username} />
          </>
        )}
        {state.db_type === "sqlite" && (
          <ReviewRow label="File" value={state.database} />
        )}
        <ReviewRow label="Password" value={state.password ? "••••••••" : "—"} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Slide-over panel
// ---------------------------------------------------------------------------

const overlayVariants: Variants = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { duration: 0.2 } },
};

const panelVariants: Variants = {
  hidden: { x: "100%" },
  show: { x: 0, transition: { type: "spring", stiffness: 300, damping: 30 } },
};

const stepVariants: Variants = {
  enter: (dir: number) => ({ x: dir > 0 ? 32 : -32, opacity: 0 }),
  center: { x: 0, opacity: 1, transition: { duration: 0.25 } },
  exit: (dir: number) => ({ x: dir > 0 ? -32 : 32, opacity: 0, transition: { duration: 0.2 } }),
};

interface ConnectionWizardProps {
  onClose: () => void;
}

export function ConnectionWizard({ onClose }: ConnectionWizardProps) {
  const [step, setStep] = useState(0);
  const [direction, setDirection] = useState(1);
  const [state, setState] = useState<WizardState>(DEFAULTS);
  const { mutate, isPending, isSuccess } = useCreateConnection();

  function go(next: number) {
    setDirection(next > step ? 1 : -1);
    setStep(next);
  }

  function canAdvance() {
    if (step === 0) return state.db_type !== "";
    if (step === 1) {
      if (!state.name) return false;
      if (!state.database) return false;
      if (state.db_type !== "sqlite" && !state.host) return false;
      return true;
    }
    return true;
  }

  function handleSave() {
    if (!state.db_type) return;
    const payload: ConnectionCreate = {
      name: state.name,
      db_type: state.db_type as DbType,
      host: state.host || undefined,
      port: state.port ? Number(state.port) : undefined,
      database: state.database || undefined,
      username: state.username || undefined,
      password: state.password || undefined,
    };
    mutate(payload, {
      onSuccess: () => {
        // stay on step 2 to show success state
      },
    });
  }

  const isLastStep = step === STEPS.length - 1;

  return (
    <>
      {/* Backdrop */}
      <motion.div
        variants={overlayVariants}
        initial="hidden"
        animate="show"
        exit="hidden"
        className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Panel */}
      <motion.div
        variants={panelVariants}
        initial="hidden"
        animate="show"
        exit="hidden"
        role="dialog"
        aria-modal="true"
        aria-label="Add database connection"
        className={cn(
          "fixed right-0 top-0 z-50 flex h-full w-full max-w-md flex-col",
          "border-l border-border bg-card shadow-2xl"
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-5 py-4 shrink-0">
          <div className="flex items-center gap-3">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/10">
              <Server className="h-4 w-4 text-primary" aria-hidden="true" />
            </div>
            <span className="text-sm font-semibold text-foreground">
              Add Connection
            </span>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={onClose}
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        {/* Progress */}
        <div className="border-b border-border px-5 py-3 shrink-0">
          <StepDots current={step} />
          <p className="mt-2 text-xs text-muted-foreground">{STEPS[step]}</p>
        </div>

        {/* Step content — animated */}
        <div className="flex-1 overflow-hidden relative">
          <AnimatePresence custom={direction} mode="wait">
            <motion.div
              key={step}
              custom={direction}
              variants={stepVariants}
              initial="enter"
              animate="center"
              exit="exit"
              className="absolute inset-0 overflow-y-auto px-5 py-5"
            >
              {step === 0 && (
                <Step1DbType state={state} onChange={setState} />
              )}
              {step === 1 && (
                <Step2Credentials state={state} onChange={setState} />
              )}
              {step === 2 && (
                <Step3Review state={state} isSuccess={isSuccess} />
              )}
            </motion.div>
          </AnimatePresence>
        </div>

        {/* Footer navigation */}
        {!isSuccess && (
          <div className="border-t border-border px-5 py-4 flex items-center justify-between shrink-0">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => (step === 0 ? onClose() : go(step - 1))}
              disabled={isPending}
            >
              <ChevronLeft className="mr-1 h-4 w-4" />
              {step === 0 ? "Cancel" : "Back"}
            </Button>

            {isLastStep ? (
              <Button
                size="sm"
                onClick={handleSave}
                disabled={isPending || !canAdvance()}
                className="gap-1.5"
              >
                {isPending ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    Saving…
                  </>
                ) : (
                  <>
                    Save connection
                    <CheckCircle2 className="h-3.5 w-3.5" />
                  </>
                )}
              </Button>
            ) : (
              <Button
                size="sm"
                onClick={() => go(step + 1)}
                disabled={!canAdvance()}
              >
                Next
                <ChevronRight className="ml-1 h-4 w-4" />
              </Button>
            )}
          </div>
        )}

        {isSuccess && (
          <div className="border-t border-border px-5 py-4 flex justify-end shrink-0">
            <Button size="sm" onClick={onClose}>
              Done
            </Button>
          </div>
        )}
      </motion.div>
    </>
  );
}
