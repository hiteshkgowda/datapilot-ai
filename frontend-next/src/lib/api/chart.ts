import { api } from "./client";
import type { ChartResponse } from "./types";

const PREFIX = "/api/v1";

export interface AskRequest {
  dataset_id: string;
  question: string;
}

export async function askQuestion(request: AskRequest): Promise<ChartResponse> {
  return api.post<ChartResponse>(`${PREFIX}/chart`, request, {
    // LLM-backed: allow up to 120 s before timing out
    timeoutMs: 120_000,
  });
}
