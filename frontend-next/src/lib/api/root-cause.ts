import { api, LLM_TIMEOUT_MS } from "./client";
import type { RootCauseRequest, RootCauseResponse } from "./types";

const PREFIX = "/api/v1";

export async function analyzeRootCause(
  request: RootCauseRequest
): Promise<RootCauseResponse> {
  return api.post<RootCauseResponse>(`${PREFIX}/root-cause`, request, {
    timeoutMs: LLM_TIMEOUT_MS,
  });
}
