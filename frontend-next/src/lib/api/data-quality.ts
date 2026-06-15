import { api } from "./client";
import type { DataQualityResponse } from "./types";

const PREFIX = "/api/v1";

export async function getDataQuality(datasetId: string): Promise<DataQualityResponse> {
  return api.get<DataQualityResponse>(`${PREFIX}/datasets/${encodeURIComponent(datasetId)}/quality`);
}
