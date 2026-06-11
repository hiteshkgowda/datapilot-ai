"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Zap } from "lucide-react";

const PHASES = [
  "Planning analysis…",
  "Executing query…",
  "Formatting results…",
] as const;

const PHASE_DELAYS_MS = [0, 2200, 6000];

export function TypingIndicator() {
  const [phase, setPhase] = useState(0);

  useEffect(() => {
    const timers = PHASE_DELAYS_MS.slice(1).map((delay, i) =>
      setTimeout(() => setPhase(i + 1), delay)
    );
    return () => timers.forEach(clearTimeout);
  }, []);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -4 }}
      transition={{ duration: 0.2, ease: "easeOut" }}
      className="flex items-start gap-4"
      role="status"
      aria-label="Analyzing…"
    >
      {/* Avatar */}
      <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-gradient-primary elevation-glow-sm">
        <Zap className="h-3 w-3 text-white" aria-hidden="true" />
      </div>

      {/* Phase label + dots */}
      <div className="flex items-center gap-2.5 pt-0.5">
        <AnimatePresence mode="wait">
          <motion.span
            key={phase}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.18, ease: "easeOut" }}
            className="text-sm text-muted-foreground"
          >
            {PHASES[phase]}
          </motion.span>
        </AnimatePresence>

        <div className="flex items-center gap-1" aria-hidden="true">
          {[0, 1, 2].map((i) => (
            <motion.span
              key={i}
              className="block h-1 w-1 rounded-full bg-primary/60"
              animate={{ opacity: [0.25, 1, 0.25], scale: [0.7, 1.1, 0.7] }}
              transition={{
                duration: 1.4,
                repeat: Infinity,
                ease: "easeInOut",
                delay: i * 0.22,
              }}
            />
          ))}
        </div>
      </div>
    </motion.div>
  );
}
