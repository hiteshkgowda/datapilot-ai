import { api } from "./client";
import type {
  AgentApproveRequest,
  AgentExplainResponse,
  AgentRunRequest,
  AgentRunResponse,
  AgentSessionInfo,
} from "./types";

const PREFIX = "/api/v1/agent";

export async function runAgent(request: AgentRunRequest): Promise<AgentRunResponse> {
  return api.post<AgentRunResponse>(`${PREFIX}/run`, request);
}

export async function resumeAgent(
  sessionId: string,
  request: AgentApproveRequest
): Promise<AgentRunResponse> {
  return api.post<AgentRunResponse>(`${PREFIX}/resume/${sessionId}`, request);
}

export async function explainAgent(
  request: AgentRunRequest
): Promise<AgentExplainResponse> {
  return api.post<AgentExplainResponse>(`${PREFIX}/explain`, request);
}

export async function getAgentSession(
  sessionId: string
): Promise<AgentSessionInfo> {
  return api.get<AgentSessionInfo>(`${PREFIX}/session/${sessionId}`);
}
