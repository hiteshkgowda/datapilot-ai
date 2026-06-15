import { api, LLM_TIMEOUT_MS } from "./client";
import type { AnomalyRequest, AnomalyResponse } from "./types";

const PREFIX = "/api/v1";

export async function detectAnomalies(
  request: AnomalyRequest
): Promise<AnomalyResponse> {
  return api.post<AnomalyResponse>(`${PREFIX}/anomalies`, request, {
    timeoutMs: LLM_TIMEOUT_MS,
  });
}
