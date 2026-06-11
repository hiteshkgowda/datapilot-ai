"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import type { Variants } from "framer-motion";
import {
  CheckCircle2,
  ChevronRight,
  Database,
  Loader2,
  Trash2,
  XCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { formatRelativeTime } from "@/lib/format";
import {
  useDeleteConnection,
  useTestConnection,
} from "@/hooks/use-connections";
import type { ConnectionMetadata } from "@/lib/api/types";

export const cardVariants: Variants = {
  hidden: { opacity: 0, y: 16 },
  show: { opacity: 1, y: 0, transition: { duration: 0.3 } },
};

const DB_LABELS: Record<string, string> = {
  sqlite: "SQLite",
  postgresql: "PostgreSQL",
  mysql: "MySQL",
};

const DB_COLORS: Record<string, string> = {
  sqlite: "text-sky-400 bg-sky-400/10 border-sky-400/20",
  postgresql: "text-blue-400 bg-blue-400/10 border-blue-400/20",
  mysql: "text-orange-400 bg-orange-400/10 border-orange-400/20",
};

interface ConnectionCardProps {
  connection: ConnectionMetadata;
  onBrowse: (id: string) => void;
}

export function ConnectionCard({ connection, onBrowse }: ConnectionCardProps) {
  const [testStatus, setTestStatus] = useState<"idle" | "ok" | "fail">("idle");
  const { mutate: test, isPending: isTesting } = useTestConnection();
  const { mutate: remove, isPending: isDeleting } = useDeleteConnection();
  const [confirmDelete, setConfirmDelete] = useState(false);

  function handleTest() {
    setTestStatus("idle");
    test(connection.id, {
      onSuccess: (res) => setTestStatus(res.status === "ok" ? "ok" : "fail"),
      onError: () => setTestStatus("fail"),
    });
  }

  function handleDelete() {
    if (!confirmDelete) {
      setConfirmDelete(true);
      return;
    }
    remove(connection.id);
  }

  const colorClass = DB_COLORS[connection.db_type] ?? "text-muted-foreground bg-muted/30";

  return (
    <motion.div
      variants={cardVariants}
      whileHover={{ y: -2, transition: { duration: 0.15 } }}
      className={cn(
        "group relative rounded-xl border border-border/50",
        "bg-card/60 backdrop-blur-sm p-5",
        "hover:border-primary/30 hover:shadow-lg hover:shadow-primary/5",
        "transition-colors duration-200"
      )}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3 mb-4">
        <div className="flex items-center gap-3 min-w-0">
          <div
            className={cn(
              "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border",
              colorClass
            )}
          >
            <Database className="h-4 w-4" aria-hidden="true" />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-foreground truncate">
              {connection.name}
            </p>
            <p className="text-[11px] text-muted-foreground truncate">
              {connection.host
                ? `${connection.host}${connection.port ? `:${connection.port}` : ""}${connection.database ? `/${connection.database}` : ""}`
                : connection.database ?? "—"}
            </p>
          </div>
        </div>

        <Badge
          variant="muted"
          className={cn("shrink-0 text-[11px]", colorClass)}
        >
          {DB_LABELS[connection.db_type] ?? connection.db_type}
        </Badge>
      </div>

      {/* Test status */}
      {testStatus !== "idle" && (
        <div
          className={cn(
            "flex items-center gap-1.5 text-xs mb-3 rounded-lg px-3 py-1.5",
            testStatus === "ok"
              ? "text-emerald-400 bg-emerald-400/10"
              : "text-destructive bg-destructive/10"
          )}
        >
          {testStatus === "ok" ? (
            <CheckCircle2 className="h-3.5 w-3.5" />
          ) : (
            <XCircle className="h-3.5 w-3.5" />
          )}
          <span>{testStatus === "ok" ? "Connection OK" : "Connection failed"}</span>
        </div>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] text-muted-foreground">
          {formatRelativeTime(connection.created_at)}
        </span>

        <div className="flex items-center gap-1">
          {/* Test */}
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-xs text-muted-foreground hover:text-foreground"
            onClick={handleTest}
            disabled={isTesting || isDeleting}
          >
            {isTesting ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              "Test"
            )}
          </Button>

          {/* Browse tables */}
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-xs text-muted-foreground hover:text-primary"
            onClick={() => onBrowse(connection.id)}
            disabled={isDeleting}
          >
            Tables
            <ChevronRight className="ml-0.5 h-3 w-3" />
          </Button>

          {/* Delete (two-step) */}
          <Button
            variant="ghost"
            size="sm"
            className={cn(
              "h-7 text-xs",
              confirmDelete
                ? "text-destructive hover:text-destructive hover:bg-destructive/10"
                : "text-muted-foreground hover:text-destructive"
            )}
            onClick={handleDelete}
            disabled={isDeleting}
            title={confirmDelete ? "Click again to confirm" : "Delete connection"}
          >
            {isDeleting ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <Trash2 className="h-3 w-3" />
            )}
            {confirmDelete && (
              <span className="ml-1">Confirm</span>
            )}
          </Button>
        </div>
      </div>
    </motion.div>
  );
}
