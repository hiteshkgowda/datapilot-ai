/**
 * Hand-maintained API types matching the FastAPI backend schemas.
 * Field names match the Python Pydantic models exactly (snake_case).
 *
 * Regenerate with:
 *   npx openapi-typescript http://localhost:8000/openapi.json \
 *     -o src/lib/api/types.gen.ts
 */

// ---------------------------------------------------------------------------
// Datasets
// ---------------------------------------------------------------------------

export type DatasetSource = "file" | "table";
export type FileType = "csv" | "excel";

export interface DbColumn {
  name: string;
  data_type: string;
  is_numeric: boolean;
}

export interface DatasetMetadata {
  id: string;
  filename: string;
  source: DatasetSource;
  file_type: FileType | null;
  size_bytes: number;
  rows: number;
  columns: number;
  column_names: string[];
  created_at: string; // ISO 8601
  // Table-backed datasets only
  connection_id: string | null;
  db_schema: string | null;
  table_name: string | null;
  row_limit: number | null;
  truncated: boolean | null;
  estimated_row_count: number | null;
  db_columns: DbColumn[] | null;
}

export interface DatasetListResponse {
  count: number;
  datasets: DatasetMetadata[];
}

export interface UploadResponse {
  message: string;
  dataset: DatasetMetadata;
}

export interface DatasetPreview {
  id: string;
  filename: string;
  source: DatasetSource;
  file_type: FileType | null;
  rows: number;
  columns: number;
  column_names: string[];
  data_types: Record<string, string>; // column name → pandas dtype
  preview_row_count: number;
  preview_rows: Record<string, unknown>[];
}

// ---------------------------------------------------------------------------
// Analytics (Chart)
// ---------------------------------------------------------------------------

export type ChartType = "bar" | "line" | "pie" | "scatter";

export interface ChartRequest {
  dataset_id: string;
  question: string;
}

export interface ChartResponse {
  answer: string;
  table_data: Record<string, unknown>[];
  chart_type: ChartType | null;
  chart_spec: Record<string, unknown> | null;
  execution_time_ms: number;
  total_time_ms: number;
}

// ---------------------------------------------------------------------------
// Forecast
// ---------------------------------------------------------------------------

export type ForecastOperation =
  | "forecast"
  | "anomaly_detection"
  | "timeseries_aggregate";
export type Frequency = "D" | "W" | "M" | "Q" | "Y";

export interface ForecastRequest {
  dataset_id: string;
  question: string;
}

export interface ForecastResponse {
  answer: string;
  operation: ForecastOperation;
  table_data: Record<string, unknown>[];
  chart_type: string | null;
  chart_spec: Record<string, unknown> | null;
  method_used: string;
  fallback_used: boolean;
  data_points: number;
  horizon: number;
  frequency: Frequency;
  execution_time_ms: number;
  total_time_ms: number;
}

// ---------------------------------------------------------------------------
// Reports
// ---------------------------------------------------------------------------

export interface ReportRequest {
  dataset_id: string;
  questions?: string[];
}

export interface ReportMetadata {
  report_id: string;
  report_version: string;
  generated_at: string; // ISO 8601
  dataset_id: string;
  dataset_filename: string;
  size_bytes: number;
  deterministic_section_count: number;
  ai_section_count: number;
  download_url: string;
}

export interface ReportListResponse {
  count: number;
  reports: ReportMetadata[];
}

// ---------------------------------------------------------------------------
// Connections
// ---------------------------------------------------------------------------

export type DbType = "sqlite" | "postgresql" | "mysql";

export interface ConnectionCreate {
  name: string;
  db_type: DbType;
  host?: string;
  port?: number;
  database?: string;
  username?: string;
  password?: string;
}

export interface ConnectionMetadata {
  id: string;
  name: string;
  db_type: DbType;
  host: string | null;
  port: number | null;
  database: string | null;
  username: string | null;
  created_at: string;
}

export interface ConnectionTestResult {
  status: string; // "ok" on success
  message: string;
}

export interface TableInfo {
  schema_name: string | null;
  name: string;
}

export interface TableListResponse {
  count: number;
  tables: TableInfo[];
}

export interface RegisterTableRequest {
  schema_name?: string;
  table: string;
  name?: string;
  row_limit?: number;
}

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------

export interface HealthResponse {
  status: string;
  app: string;
}

// ---------------------------------------------------------------------------
// CRUD Operations (F7)
// ---------------------------------------------------------------------------

export type CrudOperation =
  | "create"
  | "update"
  | "delete"
  | "bulk_update"
  | "soft_delete";

export type FilterOperator =
  | "eq"
  | "neq"
  | "gt"
  | "gte"
  | "lt"
  | "lte"
  | "in_"
  | "is_null"
  | "is_not_null";

export interface RowFilter {
  column: string;
  operator: FilterOperator;
  value: unknown;
}

export interface CrudPlan {
  operation: CrudOperation;
  schema_name: string | null;
  table_name: string;
  row_data: Record<string, unknown> | null;
  filters: RowFilter[] | null;
  set_values: Record<string, unknown> | null;
  soft_delete_column: string | null;
  soft_delete_value: unknown;
}

export interface CrudRequest {
  dataset_id?: string;
  connection_id?: string;
  schema_name?: string;
  table_name?: string;
  question: string;
}

export interface CrudExecuteRequest {
  connection_id: string;
  plan: CrudPlan;
  confirmation_token?: string;
  override_row_limit?: boolean;
  question?: string;
}

export interface RowPreview {
  columns: string[];
  rows: Record<string, unknown>[];
  total_count: number;
}

export interface CrudPreviewResponse {
  connection_id: string;
  plan: CrudPlan;
  preview: RowPreview;
  affected_row_count: number;
  requires_confirmation: boolean;
  confirmation_token: string | null;
  rollback_supported: boolean;
  warnings: string[];
}

export interface CrudExecuteResponse {
  operation: CrudOperation;
  table_name: string;
  affected_rows: number;
  rollback_token: string | null;
  rollback_supported: boolean;
  execution_time_ms: number;
  audit_id: string;
}

export interface RollbackRequest {
  connection_id: string;
  rollback_token: string;
}

export interface RollbackResponse {
  restored_rows: number;
  execution_time_ms: number;
  audit_id: string;
}

export interface AuditEntry {
  audit_id: string;
  timestamp: string;
  action: string;
  connection_id: string;
  schema_name: string | null;
  table_name: string;
  filters: Record<string, unknown>[] | null;
  set_values: Record<string, unknown> | null;
  row_data: Record<string, unknown> | null;
  affected_rows: number;
  rollback_token: string | null;
  rollback_supported: boolean;
  execution_time_ms: number;
  question: string;
}

export interface AuditListResponse {
  connection_id: string;
  count: number;
  entries: AuditEntry[];
}

// ---------------------------------------------------------------------------
// Agent (F9)
// ---------------------------------------------------------------------------

export type AgentStatus = "running" | "suspended" | "done" | "failed";

export interface PlannedToolCall {
  tool_name: string;
  arguments: Record<string, unknown>;
  step_label: string;
  requires_approval: boolean;
}

export interface ToolResult {
  tool_name: string;
  step_label: string;
  output: Record<string, unknown>;
  error: string | null;
  duration_ms: number;
}

export interface PendingApproval {
  session_id: string;
  step_index: number;
  step_label: string;
  preview: Record<string, unknown>;
}

export interface AgentRunRequest {
  question: string;
  dataset_id?: string;
  connection_id?: string;
  context?: string[];
  max_retries?: number;
}

export interface AgentRunResponse {
  session_id: string;
  status: AgentStatus;
  final_answer: string | null;
  completed_steps: ToolResult[];
  pending_approval: PendingApproval | null;
  error: string | null;
}

export interface AgentApproveRequest {
  approved: boolean;
}

export interface AgentExplainResponse {
  session_id: string;
  plan: PlannedToolCall[];
  plan_valid: boolean;
  warnings: string[];
  error: string | null;
}

export interface AgentSessionInfo {
  session_id: string;
  status: AgentStatus;
  user_goal: string;
  current_step: number;
  total_steps: number;
  completed_results: ToolResult[];
  pending_approval: PendingApproval | null;
  final_answer: string | null;
  error: string | null;
}
