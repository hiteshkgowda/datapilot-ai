import { api } from "./client";
import type {
  ConnectionCreate,
  ConnectionMetadata,
  ConnectionTestResult,
  DatasetMetadata,
  RegisterTableRequest,
  TableListResponse,
} from "./types";

const PREFIX = "/api/v1/connections";

export async function listConnections(): Promise<ConnectionMetadata[]> {
  return api.get<ConnectionMetadata[]>(PREFIX);
}

export async function createConnection(
  request: ConnectionCreate
): Promise<ConnectionMetadata> {
  return api.post<ConnectionMetadata>(PREFIX, request);
}

export async function deleteConnection(id: string): Promise<void> {
  return api.delete<void>(`${PREFIX}/${id}`);
}

export async function testConnection(id: string): Promise<ConnectionTestResult> {
  return api.post<ConnectionTestResult>(`${PREFIX}/${id}/test`, {});
}

export async function listTables(id: string): Promise<TableListResponse> {
  return api.get<TableListResponse>(`${PREFIX}/${id}/tables`);
}

export async function registerTable(
  connectionId: string,
  request: RegisterTableRequest
): Promise<DatasetMetadata> {
  return api.post<DatasetMetadata>(`${PREFIX}/${connectionId}/datasets`, request);
}
