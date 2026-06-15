import { api, LLM_TIMEOUT_MS } from "./client";
import type { RecommendationRequest, RecommendationResponse } from "./types";

const PREFIX = "/api/v1";

export async function generateRecommendations(
  request: RecommendationRequest
): Promise<RecommendationResponse> {
  return api.post<RecommendationResponse>(`${PREFIX}/recommendations`, request, {
    timeoutMs: LLM_TIMEOUT_MS,
  });
}
