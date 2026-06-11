"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { Variants } from "framer-motion";
import { Link2, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useConnections } from "@/hooks/use-connections";
import { ConnectionCard, cardVariants } from "./ConnectionCard";
import { ConnectionWizard } from "./ConnectionWizard";
import { TableBrowser } from "./TableBrowser";
import type { ConnectionMetadata } from "@/lib/api/types";

const gridVariants: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.07 } },
};

function ConnectionGridSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: 3 }).map((_, i) => (
        <div
          key={i}
          className="rounded-xl border border-border/30 bg-card/40 p-5 space-y-4"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Skeleton className="h-9 w-9 rounded-lg shrink-0" />
              <div className="space-y-1.5">
                <Skeleton className="h-4 w-28" />
                <Skeleton className="h-3 w-40" />
              </div>
            </div>
            <Skeleton className="h-5 w-20 rounded-full" />
          </div>
          <div className="flex justify-between items-center">
            <Skeleton className="h-3 w-20" />
            <div className="flex gap-1">
              <Skeleton className="h-7 w-10" />
              <Skeleton className="h-7 w-16" />
              <Skeleton className="h-7 w-7" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

export function ConnectionsWorkspace() {
  const { data, isLoading } = useConnections();
  const connections = data ?? [];

  const [showWizard, setShowWizard] = useState(false);
  const [browsing, setBrowsing] = useState<ConnectionMetadata | null>(null);

  function handleBrowse(id: string) {
    const conn = connections.find((c) => c.id === id);
    if (conn) setBrowsing(conn);
  }

  return (
    <>
      <div className="mx-auto max-w-5xl space-y-8">
        {/* Header */}
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10">
              <Link2 className="h-5 w-5 text-primary" aria-hidden="true" />
            </div>
            <div>
              <h1 className="text-lg font-semibold text-foreground">
                Database Connections
              </h1>
              <p className="text-sm text-muted-foreground">
                Connect to databases and register tables as datasets
              </p>
            </div>
          </div>

          <Button
            size="sm"
            className="gap-1.5 shrink-0"
            onClick={() => setShowWizard(true)}
          >
            <Plus className="h-4 w-4" />
            Add connection
          </Button>
        </div>

        {/* Table browser (replaces grid when browsing) */}
        <AnimatePresence mode="wait">
          {browsing ? (
            <motion.div
              key="browser"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
            >
              <TableBrowser
                connection={browsing}
                onClose={() => setBrowsing(null)}
              />
            </motion.div>
          ) : (
            <motion.div
              key="grid"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
            >
              {isLoading ? (
                <ConnectionGridSkeleton />
              ) : connections.length === 0 ? (
                <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border/50 bg-card/20 py-20 text-center">
                  <Link2
                    className="mb-3 h-10 w-10 text-muted-foreground/30"
                    aria-hidden="true"
                  />
                  <p className="text-sm font-medium text-muted-foreground">
                    No connections yet
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground/60">
                    Add a database connection to browse and register tables
                  </p>
                  <Button
                    size="sm"
                    className="mt-4 gap-1.5"
                    onClick={() => setShowWizard(true)}
                  >
                    <Plus className="h-4 w-4" />
                    Add your first connection
                  </Button>
                </div>
              ) : (
                <motion.div
                  variants={gridVariants}
                  initial="hidden"
                  animate="show"
                  className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
                >
                  {connections.map((conn) => (
                    <motion.div key={conn.id} variants={cardVariants}>
                      <ConnectionCard
                        connection={conn}
                        onBrowse={handleBrowse}
                      />
                    </motion.div>
                  ))}
                </motion.div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Slide-over wizard */}
      <AnimatePresence>
        {showWizard && (
          <ConnectionWizard onClose={() => setShowWizard(false)} />
        )}
      </AnimatePresence>
    </>
  );
}
