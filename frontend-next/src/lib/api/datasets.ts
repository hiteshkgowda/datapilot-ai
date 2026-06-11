import { api, apiFetch, ApiError } from "./client";
import type {
  DatasetListResponse,
  DatasetPreview,
  UploadResponse,
} from "./types";

const PREFIX = "/api/v1";

export async function listDatasets(): Promise<DatasetListResponse> {
  return api.get<DatasetListResponse>(`${PREFIX}/datasets`);
}

export async function getDatasetPreview(
  id: string,
  limit = 10
): Promise<DatasetPreview> {
  return api.get<DatasetPreview>(
    `${PREFIX}/datasets/${encodeURIComponent(id)}/preview?limit=${limit}`
  );
}

export async function uploadDataset(file: File): Promise<UploadResponse> {
  const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
  const endpoint =
    ext === "xlsx" || ext === "xls"
      ? `${PREFIX}/datasets/upload/excel`
      : `${PREFIX}/datasets/upload/csv`;

  const form = new FormData();
  form.append("file", file);

  // Do NOT set Content-Type — browser must set the multipart boundary.
  const res = await fetch(
    `${process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000"}${endpoint}`,
    { method: "POST", body: form }
  );

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const json = await res.json();
      if (typeof json?.detail === "string") detail = json.detail;
    } catch {
      detail = res.statusText || detail;
    }
    throw new ApiError(res.status, detail, null);
  }

  return res.json() as Promise<UploadResponse>;
}

export { ApiError };
