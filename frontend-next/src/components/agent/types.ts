/**
 * Local component types for the Agent Workspace (F9).
 * These are separate from the API types — they represent the in-memory
 * conversation state managed by AgentWorkspace.
 */

import type {
  AgentExplainResponse,
  AgentStatus,
  PendingApproval,
  PlannedToolCall,
  ToolResult,
} from "@/lib/api/types";

// ---------------------------------------------------------------------------
// Conversation turns rendered by AgentThread
// ---------------------------------------------------------------------------

export interface AgentUserTurn {
  role: "user";
  id: string;
  timestamp: string;
  content: string;
}

export interface AgentResponseTurn {
  role: "agent";
  id: string;
  timestamp: string;
  answer: string;
  steps: ToolResult[];
  status: AgentStatus;
  sessionId: string;
  error: string | null;
}

export interface AgentApprovalTurn {
  role: "approval";
  id: string;
  timestamp: string;
  approval: PendingApproval;
  sessionId: string;
}

export interface AgentExplainTurn {
  role: "explain";
  id: string;
  timestamp: string;
  goal: string;
  explain: AgentExplainResponse;
}

export interface AgentErrorTurn {
  role: "error";
  id: string;
  timestamp: string;
  message: string;
}

export type AgentConversationTurn =
  | AgentUserTurn
  | AgentResponseTurn
  | AgentApprovalTurn
  | AgentExplainTurn
  | AgentErrorTurn;

// ---------------------------------------------------------------------------
// Session stored in localStorage
// ---------------------------------------------------------------------------

export interface StoredSession {
  id: string;
  goal: string;
  timestamp: string;
  status: AgentStatus;
  turns: AgentConversationTurn[];
  completedSteps: ToolResult[];
  pendingApproval: PendingApproval | null;
  finalAnswer: string | null;
  error: string | null;
}

// ---------------------------------------------------------------------------
// Context attached to a goal request (optional dataset / connection)
// ---------------------------------------------------------------------------

export interface AgentContext {
  datasetId: string;
  connectionId: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

export function uid(): string {
  return typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

export const MAX_STORED_SESSIONS = 30;
export const SESSION_STORAGE_KEY = "uda-agent-sessions";

export function loadSessions(): StoredSession[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(SESSION_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as StoredSession[]) : [];
  } catch {
    return [];
  }
}

export function saveSessions(sessions: StoredSession[]): void {
  try {
    localStorage.setItem(
      SESSION_STORAGE_KEY,
      JSON.stringify(sessions.slice(0, MAX_STORED_SESSIONS))
    );
  } catch {
    // quota exceeded — silently drop
  }
}

// Re-export PlannedToolCall for convenience inside the agent component tree
export type { PlannedToolCall };
