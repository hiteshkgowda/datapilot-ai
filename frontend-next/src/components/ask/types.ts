import type { ChartType } from "@/lib/api/types";

export interface UserTurn {
  role: "user";
  id: string;
  timestamp: string;
  content: string;
}

export interface AssistantTurn {
  role: "assistant";
  id: string;
  timestamp: string;
  answer: string;
  table_data: Record<string, unknown>[];
  chart_type: ChartType | null;
  chart_spec: Record<string, unknown> | null;
  execution_time_ms: number;
  total_time_ms: number;
}

export interface ErrorTurn {
  role: "error";
  id: string;
  timestamp: string;
  message: string;
}

export type ConversationTurn = UserTurn | AssistantTurn | ErrorTurn;
