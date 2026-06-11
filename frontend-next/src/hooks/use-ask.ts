"use client";

import { useCallback, useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { askQuestion } from "@/lib/api/chart";
import { ApiError } from "@/lib/api/client";
import type {
  AssistantTurn,
  ConversationTurn,
  ErrorTurn,
  UserTurn,
} from "@/components/ask/types";

function storageKey(datasetId: string) {
  return `uda-ask-${datasetId}`;
}

function loadHistory(datasetId: string): ConversationTurn[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(storageKey(datasetId));
    return raw ? (JSON.parse(raw) as ConversationTurn[]) : [];
  } catch {
    return [];
  }
}

function persistHistory(datasetId: string, turns: ConversationTurn[]) {
  try {
    // Keep at most 50 turns to bound localStorage usage
    const capped = turns.slice(-50);
    localStorage.setItem(storageKey(datasetId), JSON.stringify(capped));
  } catch {
    // Storage quota exceeded — silently ignore
  }
}

function uid(): string {
  return typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

export function useAsk(datasetId: string) {
  // Initialize empty — localStorage is not available during SSR.
  // The effect below loads history after mount and re-runs on dataset change.
  const [turns, setTurns] = useState<ConversationTurn[]>([]);

  useEffect(() => {
    setTurns(loadHistory(datasetId));
  }, [datasetId]);

  // Persist on every change
  useEffect(() => {
    persistHistory(datasetId, turns);
  }, [datasetId, turns]);

  const mutation = useMutation({
    mutationFn: (question: string) =>
      askQuestion({ dataset_id: datasetId, question }),

    onSuccess: (data) => {
      const turn: AssistantTurn = {
        role: "assistant",
        id: uid(),
        timestamp: new Date().toISOString(),
        answer: data.answer,
        table_data: data.table_data,
        chart_type: data.chart_type,
        chart_spec: data.chart_spec,
        execution_time_ms: data.execution_time_ms,
        total_time_ms: data.total_time_ms,
      };
      setTurns((prev) => [...prev, turn]);
    },

    onError: (err: unknown) => {
      const message =
        err instanceof ApiError
          ? err.message
          : "Something went wrong. Please try again.";
      toast.error(message);
      const turn: ErrorTurn = {
        role: "error",
        id: uid(),
        timestamp: new Date().toISOString(),
        message,
      };
      setTurns((prev) => [...prev, turn]);
    },
  });

  const sendQuestion = useCallback(
    (question: string) => {
      const trimmed = question.trim();
      if (!trimmed || mutation.isPending) return;

      const userTurn: UserTurn = {
        role: "user",
        id: uid(),
        timestamp: new Date().toISOString(),
        content: trimmed,
      };
      setTurns((prev) => [...prev, userTurn]);
      mutation.mutate(trimmed);
    },
    [mutation]
  );

  const clearHistory = useCallback(() => {
    setTurns([]);
    try {
      localStorage.removeItem(storageKey(datasetId));
    } catch {}
  }, [datasetId]);

  return {
    turns,
    sendQuestion,
    clearHistory,
    isPending: mutation.isPending,
  };
}
