import { api, LLM_TIMEOUT_MS } from "./client";
import type { InsightRequest, InsightResponse } from "./types";

const PREFIX = "/api/v1";

export async function generateInsights(
  request: InsightRequest
): Promise<InsightResponse> {
  return api.post<InsightResponse>(`${PREFIX}/insights/generate`, request, {
    timeoutMs: LLM_TIMEOUT_MS,
  });
}
