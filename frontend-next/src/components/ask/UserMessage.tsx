"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { formatRelativeTime } from "@/lib/format";
import type { UserTurn } from "./types";

interface UserMessageProps {
  turn: UserTurn;
}

export function UserMessage({ turn }: UserMessageProps) {
  const [showTime, setShowTime] = useState(false);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: "easeOut" }}
      className="flex justify-end"
    >
      <div
        className="flex flex-col items-end gap-1.5 max-w-[65%]"
        onMouseEnter={() => setShowTime(true)}
        onMouseLeave={() => setShowTime(false)}
      >
        <div className="rounded-2xl bg-primary px-4 py-2.5">
          <p className="text-sm text-primary-foreground leading-relaxed whitespace-pre-wrap">
            {turn.content}
          </p>
        </div>

        <motion.span
          initial={false}
          animate={{ opacity: showTime ? 1 : 0 }}
          transition={{ duration: 0.15 }}
          className={cn(
            "text-[10px] text-muted-foreground/50 pr-0.5 select-none",
            !showTime && "pointer-events-none"
          )}
          aria-hidden={!showTime}
        >
          {formatRelativeTime(turn.timestamp)}
        </motion.span>
      </div>
    </motion.div>
  );
}
