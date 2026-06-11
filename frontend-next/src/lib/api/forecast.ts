import { api } from "./client";
import type { ForecastRequest, ForecastResponse } from "./types";

const PREFIX = "/api/v1";

export async function runForecast(
  request: ForecastRequest
): Promise<ForecastResponse> {
  return api.post<ForecastResponse>(`${PREFIX}/forecast`, request, {
    timeoutMs: 120_000,
  });
}
