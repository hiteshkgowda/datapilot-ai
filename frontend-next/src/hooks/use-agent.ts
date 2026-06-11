"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  explainAgent,
  getAgentSession,
  resumeAgent,
  runAgent,
} from "@/lib/api/agent";
import type {
  AgentApproveRequest,
  AgentRunRequest,
} from "@/lib/api/types";

export function useAgentRun() {
  return useMutation({
    mutationFn: (request: AgentRunRequest) => runAgent(request),
    onError: (err: Error) => {
      toast.error("Agent run failed", { description: err.message });
    },
  });
}

export function useAgentResume() {
  return useMutation({
    mutationFn: ({
      sessionId,
      request,
    }: {
      sessionId: string;
      request: AgentApproveRequest;
    }) => resumeAgent(sessionId, request),
    onError: (err: Error) => {
      toast.error("Resume failed", { description: err.message });
    },
  });
}

export function useAgentExplain() {
  return useMutation({
    mutationFn: (request: AgentRunRequest) => explainAgent(request),
    onError: (err: Error) => {
      toast.error("Explain failed", { description: err.message });
    },
  });
}

export function useAgentSession(sessionId: string | null) {
  return useQuery({
    queryKey: ["agent-session", sessionId],
    queryFn: () => getAgentSession(sessionId!),
    enabled: !!sessionId,
    staleTime: 5_000,
    retry: false,
  });
}
