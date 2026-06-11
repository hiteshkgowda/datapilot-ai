"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Zap } from "lucide-react";

const PHASES = ["Planning…", "Executing tools…", "Processing results…"];
const PHASE_DELAYS_MS = [0, 3500, 9000];

export function AgentThinkingIndicator() {
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
      exit={{ opacity: 0, transition: { duration: 0.15 } }}
      transition={{ duration: 0.2, ease: "easeOut" }}
      className="flex items-center gap-3"
    >
      {/* Gradient avatar dot */}
      <div
        className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-gradient-primary elevation-glow-sm"
        aria-hidden="true"
      >
        <Zap className="h-3 w-3 text-white" />
      </div>

      <div className="flex items-center gap-2">
        <AnimatePresence mode="wait">
          <motion.span
            key={phase}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.15 }}
            className="text-sm text-muted-foreground"
          >
            {PHASES[phase]}
          </motion.span>
        </AnimatePresence>

        {/* Animated dots */}
        <div className="flex items-center gap-0.5">
          {[0, 1, 2].map((i) => (
            <motion.span
              key={i}
              className="inline-block h-1 w-1 rounded-full bg-primary/50"
              animate={{ opacity: [0.3, 1, 0.3] }}
              transition={{ duration: 1.2, repeat: Infinity, delay: i * 0.2 }}
            />
          ))}
        </div>
      </div>
    </motion.div>
  );
}
