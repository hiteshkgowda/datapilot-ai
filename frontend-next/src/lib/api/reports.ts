import { api } from "./client";
import type { ReportListResponse, ReportMetadata } from "./types";

const PREFIX = "/api/v1/reports";
const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

export async function generateReport(
  datasetId: string,
  questions: string[]
): Promise<ReportMetadata> {
  return api.post<ReportMetadata>(PREFIX, { dataset_id: datasetId, questions }, { timeoutMs: 120_000 });
}

export async function listReports(): Promise<ReportListResponse> {
  return api.get<ReportListResponse>(PREFIX);
}

/** Returns the direct URL to stream the PDF — use as an <a href> or window.open. */
export function reportDownloadUrl(reportId: string): string {
  return `${BACKEND_URL}${PREFIX}/${reportId}/download`;
}
