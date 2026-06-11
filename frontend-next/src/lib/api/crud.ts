import { api } from "./client";
import type {
  AuditListResponse,
  CrudExecuteRequest,
  CrudExecuteResponse,
  CrudPreviewResponse,
  CrudRequest,
  RollbackRequest,
  RollbackResponse,
} from "./types";

const PREFIX = "/api/v1/crud";

export async function previewCrud(
  request: CrudRequest
): Promise<CrudPreviewResponse> {
  return api.post<CrudPreviewResponse>(`${PREFIX}/preview`, request);
}

export async function executeCrud(
  request: CrudExecuteRequest
): Promise<CrudExecuteResponse> {
  return api.post<CrudExecuteResponse>(`${PREFIX}/execute`, request);
}

export async function rollbackCrud(
  request: RollbackRequest
): Promise<RollbackResponse> {
  return api.post<RollbackResponse>(`${PREFIX}/rollback`, request);
}

export async function getAuditLog(
  connectionId: string
): Promise<AuditListResponse> {
  return api.get<AuditListResponse>(`${PREFIX}/audit/${connectionId}`);
}
