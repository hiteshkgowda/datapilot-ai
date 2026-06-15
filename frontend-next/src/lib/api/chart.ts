import { api, LLM_TIMEOUT_MS } from "./client";
import type { ChartResponse } from "./types";

const PREFIX = "/api/v1";

export interface AskRequest {
  dataset_id: string;
  question: string;
}

export async function askQuestion(request: AskRequest): Promise<ChartResponse> {
  return api.post<ChartResponse>(`${PREFIX}/chart`, request, {
    timeoutMs: LLM_TIMEOUT_MS,
  });
}
