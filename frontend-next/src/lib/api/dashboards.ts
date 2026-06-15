import { api, LLM_TIMEOUT_MS } from "./client";
import type {
  DashboardConfig,
  DashboardListResponse,
  GenerateDashboardRequest,
  GenerateDashboardResponse,
  SaveDashboardRequest,
  SaveDashboardResponse,
} from "./types";

const PREFIX = "/api/v1";

export async function generateDashboard(
  request: GenerateDashboardRequest
): Promise<GenerateDashboardResponse> {
  return api.post<GenerateDashboardResponse>(
    `${PREFIX}/dashboards/generate`,
    request,
    { timeoutMs: LLM_TIMEOUT_MS }
  );
}

export async function saveDashboard(
  request: SaveDashboardRequest
): Promise<SaveDashboardResponse> {
  return api.post<SaveDashboardResponse>(`${PREFIX}/dashboards/save`, request);
}

export async function getDashboard(id: string): Promise<DashboardConfig> {
  return api.get<DashboardConfig>(`${PREFIX}/dashboards/${id}`);
}

export async function listDashboards(): Promise<DashboardListResponse> {
  return api.get<DashboardListResponse>(`${PREFIX}/dashboards`);
}
