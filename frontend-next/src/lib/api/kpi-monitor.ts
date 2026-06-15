import { api } from "./client";
import type { KPIMonitorResponse } from "./types";

const PREFIX = "/api/v1";

export async function getKPIMonitor(
  datasetId: string,
  maxKpis = 12
): Promise<KPIMonitorResponse> {
  return api.get<KPIMonitorResponse>(
    `${PREFIX}/datasets/${encodeURIComponent(datasetId)}/monitor?max_kpis=${maxKpis}`
  );
}
