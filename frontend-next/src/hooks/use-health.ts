"use client";

import { useQuery } from "@tanstack/react-query";

const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

interface HealthResponse {
  status: string;
  app: string;
  storage?: {
    status?: string;
    ephemeral?: boolean;
  };
}

async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch(`${BACKEND_URL}/health`, {
    signal: AbortSignal.timeout(5_000),
  });
  if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
  return res.json() as Promise<HealthResponse>;
}

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    staleTime: 0,
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
    retry: 1,
  });
}
