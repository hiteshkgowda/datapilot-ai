"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowLeft,
  CheckCircle2,
  Database,
  Loader2,
  Plus,
  Table2,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { useListTables, useRegisterTable } from "@/hooks/use-connections";
import type { ConnectionMetadata } from "@/lib/api/types";

interface TableBrowserProps {
  connection: ConnectionMetadata;
  onClose: () => void;
}

export function TableBrowser({ connection, onClose }: TableBrowserProps) {
  const { data, isLoading, error } = useListTables(connection.id, true);
  const { mutate: register, isPending: isRegistering } = useRegisterTable(
    connection.id
  );
  const [registering, setRegistering] = useState<string | null>(null);
  const [registered, setRegistered] = useState<Set<string>>(new Set());

  const tables = data?.tables ?? [];

  function handleRegister(tableName: string, schemaName: string | null) {
    setRegistering(tableName);
    register(
      { table: tableName, schema_name: schemaName ?? undefined },
      {
        onSuccess: () => {
          setRegistered((s) => new Set(s).add(tableName));
          setRegistering(null);
        },
        onError: () => setRegistering(null),
      }
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, x: 24 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 24 }}
      transition={{ duration: 0.25 }}
      className="rounded-xl border border-border/50 bg-card/60 backdrop-blur-sm overflow-hidden"
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border/50 px-5 py-4">
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 shrink-0"
            onClick={onClose}
            aria-label="Back to connections"
          >
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div className="flex items-center gap-2">
            <Database className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
            <span className="text-sm font-semibold text-foreground">
              {connection.name}
            </span>
          </div>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          onClick={onClose}
          aria-label="Close browser"
        >
          <X className="h-4 w-4" />
        </Button>
      </div>

      {/* Body */}
      <div className="p-5 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Discovered tables
          </h3>
          {data && (
            <span className="text-[11px] text-muted-foreground">
              {data.count} table{data.count !== 1 ? "s" : ""}
            </span>
          )}
        </div>

        {isLoading && (
          <div className="space-y-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <div
                key={i}
                className="flex items-center justify-between rounded-lg border border-border/30 px-4 py-3"
              >
                <div className="flex items-center gap-2">
                  <Skeleton className="h-4 w-4 rounded" />
                  <Skeleton className="h-4 w-32" />
                </div>
                <Skeleton className="h-7 w-20 rounded-lg" />
              </div>
            ))}
          </div>
        )}

        {error && (
          <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-xs text-destructive">
            Failed to discover tables: {error.message}
          </div>
        )}

        {!isLoading && tables.length === 0 && !error && (
          <div className="flex flex-col items-center justify-center py-10 text-center">
            <Table2
              className="mb-2 h-8 w-8 text-muted-foreground/30"
              aria-hidden="true"
            />
            <p className="text-sm text-muted-foreground">No tables found</p>
          </div>
        )}

        <AnimatePresence>
          {tables.map((table) => {
            const key = table.name;
            const isThisRegistering = registering === key && isRegistering;
            const isRegistered = registered.has(key);

            return (
              <motion.div
                key={key}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex items-center justify-between rounded-lg border border-border/40 bg-background/40 px-4 py-3 hover:border-border/70 transition-colors"
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  <Table2
                    className="h-4 w-4 shrink-0 text-muted-foreground"
                    aria-hidden="true"
                  />
                  <div className="min-w-0">
                    <span className="text-sm text-foreground font-mono truncate block">
                      {table.schema_name ? (
                        <span className="text-muted-foreground">{table.schema_name}.</span>
                      ) : null}
                      {table.name}
                    </span>
                  </div>
                </div>

                {isRegistered ? (
                  <Badge
                    variant="muted"
                    className="text-[11px] text-emerald-400 bg-emerald-400/10 border-emerald-400/20 gap-1"
                  >
                    <CheckCircle2 className="h-3 w-3" />
                    Registered
                  </Badge>
                ) : (
                  <Button
                    size="sm"
                    variant="ghost"
                    className={cn(
                      "h-7 text-xs text-muted-foreground hover:text-primary hover:bg-primary/5",
                      "gap-1"
                    )}
                    onClick={() => handleRegister(table.name, table.schema_name)}
                    disabled={isThisRegistering || isRegistering}
                  >
                    {isThisRegistering ? (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ) : (
                      <Plus className="h-3 w-3" />
                    )}
                    {isThisRegistering ? "Registering…" : "Register"}
                  </Button>
                )}
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}
