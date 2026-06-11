"""LLM planner for the agent layer.

The planner is a conversational AI that decides whether to:
  1. Reply directly   → {"type": "chat",  "message": "..."}
  2. Execute tools    → {"type": "plan",  "steps": [...]}

This makes the agent behave like ChatGPT — it can hold natural conversations
AND run data analysis tasks using the available tools.

Pattern: OllamaAgentPlanner / GroqAgentPlanner / FallbackAgentPlanner.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol, runtime_checkable

import httpx

from app.core.config import Settings
from app.core.exceptions import LLMError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

# Shared capability description injected into every system prompt.
_CAPABILITY_DESCRIPTION = """\
You are a helpful AI data assistant — like ChatGPT, but specialised in data analysis.

You can:
- Have natural conversations, answer general questions, and explain concepts
- Analyse uploaded datasets (CSV / Excel): answer questions, generate charts, run forecasts
- Connect to databases and run read queries or safe mutations
- Generate professional PDF reports
- Perform database mutations (insert / update / delete) with human approval

You always respond with a single JSON object. Choose the type based on the input:

  For greetings, general questions, clarifications, or when you need more info from the user:
    {"type": "chat", "message": "<your natural language reply>"}

  For data analysis tasks (requires tools):
    {"type": "plan", "steps": [<tool call objects>]}

DECISION RULES:
- Greeting / chitchat / "what can you do?" / "help"  →  type: "chat"
- General knowledge question  →  type: "chat"
- User asks about data BUT no dataset_id or connection_id is provided  →  type: "chat"
  and ask them to upload or select a dataset first
- Data question WITH a dataset_id or connection_id in context  →  type: "plan"
- Anything ambiguous  →  type: "chat" and ask a clarifying question

TOOL CALL RULES (only for type: "plan"):
1. Use ONLY the dataset_id and connection_id given in the request context. Never invent IDs.
2. Each step object must have exactly these keys:
   - "tool_name"  : string  — one of the available tool names
   - "arguments"  : object  — matching the tool's input_schema
   - "step_label" : string  — one short phrase describing this step
3. For any database mutation (insert / update / delete / soft-delete):
   - Always emit "crud_preview" first.
   - Immediately follow it with "crud_execute".
4. "report" may appear at most once.
5. "forecast" may appear at most once.
6. Set unused arguments to null or omit them.
7. Do not include "requires_approval" in arguments — it is set by the system.
"""

# Groq: response_format=json_object forces the model to return a JSON object.
# The DECISION RULES above already handle the chat/plan split correctly.
GROQ_SYSTEM_PROMPT = _CAPABILITY_DESCRIPTION

# Ollama: format="json" also forces a JSON object.
SYSTEM_PROMPT = _CAPABILITY_DESCRIPTION

# Re-planner prompts — always produce a revised tool plan (never chat).
_REPLAN_CAPABILITY = """\
You are an orchestration re-planner. A previous execution step failed.
Given the goal, completed results, the error, and the remaining un-executed steps,
produce a revised plan for only the remaining work.

Respond with:
  {"type": "plan", "steps": [<revised tool call objects>]}

If no recovery is possible, respond with:
  {"type": "plan", "steps": []}

Same tool call rules apply as for the original planner.
"""

_REPLAN_SYSTEM_PROMPT = _REPLAN_CAPABILITY
_GROQ_REPLAN_SYSTEM_PROMPT = _REPLAN_CAPABILITY


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _build_user_prompt(
    goal: str,
    tool_schemas: list[dict[str, Any]],
    dataset_id: str | None,
    connection_id: str | None,
    conversation_history: list[dict[str, Any]],
) -> str:
    tools_text = json.dumps(tool_schemas, indent=2)
    context_lines: list[str] = []
    if dataset_id:
        context_lines.append(f"dataset_id: {dataset_id}")
    if connection_id:
        context_lines.append(f"connection_id: {connection_id}")
    context_text = "\n".join(context_lines) or "none provided"

    history_text = ""
    if conversation_history:
        recent = conversation_history[-5:]
        history_text = "\n\nConversation history:\n" + "\n".join(
            f"- User: {t.get('goal', '')}  |  Assistant: {t.get('summary', '')}"
            for t in recent
        )

    return (
        f"Available tools:\n{tools_text}\n\n"
        f"Request context:\n{context_text}"
        f"{history_text}\n\n"
        f"User: {goal}\n"
        "Response (JSON):"
    )


def _build_replan_prompt(
    goal: str,
    completed_results: list[dict[str, Any]],
    failed_step: dict[str, Any],
    error: str,
    remaining_steps: list[dict[str, Any]],
    tool_schemas: list[dict[str, Any]],
) -> str:
    completed_summary = "; ".join(
        f"{r['tool_name']}: {r.get('output', {}).get('answer', 'done')}"
        for r in completed_results
    )
    tools_text = json.dumps(tool_schemas, indent=2)
    remaining_text = json.dumps(remaining_steps, indent=2)
    return (
        f"Available tools:\n{tools_text}\n\n"
        f"Goal: {goal}\n"
        f"Completed steps: {completed_summary or 'none'}\n"
        f"Failed step: {failed_step.get('tool_name')} — {failed_step.get('step_label')}\n"
        f"Error: {error}\n"
        f"Remaining planned steps (before failure):\n{remaining_text}\n\n"
        "Revised JSON plan for remaining work:"
    )


# ---------------------------------------------------------------------------
# Output parsers
# ---------------------------------------------------------------------------

def _strip_fences(content: str) -> str:
    content = content.strip()
    if content.startswith("```"):
        parts = content.split("```")
        content = parts[1] if len(parts) > 1 else content
        if content.startswith("json"):
            content = content[4:]
    return content.strip()


def _extract_steps(parsed: dict[str, Any], source: str) -> list[dict[str, Any]]:
    """Pull a steps list out of the parsed dict; raise LLMError if malformed."""
    for key in ("steps", "plan", "tool_calls", "actions"):
        if key in parsed and isinstance(parsed[key], list):
            steps = parsed[key]
            break
    else:
        # Bare single-step dict — model skipped the wrapper.
        if "tool_name" in parsed:
            steps = [parsed]
        else:
            steps = []
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            raise LLMError(f"{source} step {i} is not an object: {step!r}")
        if "tool_name" not in step:
            raise LLMError(f"{source} step {i} missing 'tool_name': {step!r}")
    return steps


def _parse_response(content: str, source: str) -> dict[str, Any]:
    """Parse the LLM output into {"type": "chat"|"plan", ...}.

    Returns:
        {"type": "chat",  "message": str}
        {"type": "plan",  "steps":   list[dict]}
    """
    content = _strip_fences(content)
    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, TypeError) as exc:
        raise LLMError(f"{source} returned invalid JSON: {content!r}") from exc

    if isinstance(parsed, list):
        # Older format — bare array of steps (Ollama legacy).
        for i, step in enumerate(parsed):
            if not isinstance(step, dict) or "tool_name" not in step:
                raise LLMError(f"{source} step {i} malformed: {step!r}")
        return {"type": "plan", "steps": parsed}

    if not isinstance(parsed, dict):
        raise LLMError(f"{source} returned unexpected JSON type: {type(parsed)}")

    response_type = parsed.get("type", "plan")

    if response_type == "chat":
        message = parsed.get("message", "").strip()
        if not message:
            # Fallback: model said "chat" but gave no message — turn into a
            # plan parse attempt so we at least try to do something useful.
            logger.warning("%s returned empty chat message; attempting plan parse.", source)
            return {"type": "plan", "steps": _extract_steps(parsed, source)}
        return {"type": "chat", "message": message}

    # type == "plan" (or missing)
    return {"type": "plan", "steps": _extract_steps(parsed, source)}


def _parse_replan(content: str, source: str) -> list[dict[str, Any]]:
    """Parse a re-plan response; always returns a list of step dicts."""
    result = _parse_response(content, source)
    return result.get("steps", [])


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class AgentPlanner(Protocol):
    async def generate_plan(
        self,
        goal: str,
        tool_schemas: list[dict[str, Any]],
        dataset_id: str | None,
        connection_id: str | None,
        conversation_history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Return {"type": "chat", "message": str} or {"type": "plan", "steps": list}."""
        ...

    async def replan(
        self,
        goal: str,
        tool_schemas: list[dict[str, Any]],
        completed_results: list[dict[str, Any]],
        failed_step: dict[str, Any],
        error: str,
        remaining_steps: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Return a revised list of step dicts for the remaining work."""
        ...


# ---------------------------------------------------------------------------
# Ollama implementation
# ---------------------------------------------------------------------------

class OllamaAgentPlanner:
    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.ollama_base_url.rstrip("/")
        self._model = settings.ollama_model
        self._client: httpx.AsyncClient | None = None

    def set_client(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def generate_plan(
        self,
        goal: str,
        tool_schemas: list[dict[str, Any]],
        dataset_id: str | None,
        connection_id: str | None,
        conversation_history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        user_prompt = _build_user_prompt(
            goal, tool_schemas, dataset_id, connection_id, conversation_history
        )
        content = await self._chat(SYSTEM_PROMPT, user_prompt)
        return _parse_response(content, "Ollama")

    async def replan(
        self,
        goal: str,
        tool_schemas: list[dict[str, Any]],
        completed_results: list[dict[str, Any]],
        failed_step: dict[str, Any],
        error: str,
        remaining_steps: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        user_prompt = _build_replan_prompt(
            goal, completed_results, failed_step, error, remaining_steps, tool_schemas
        )
        content = await self._chat(_REPLAN_SYSTEM_PROMPT, user_prompt)
        return _parse_replan(content, "Ollama")

    async def _chat(self, system: str, user: str) -> str:
        if self._client is None:
            raise LLMError("Agent LLM HTTP client not initialised.")
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1},
        }
        try:
            resp = await self._client.post(f"{self._base_url}/api/chat", json=payload)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError(f"Ollama '{self._model}' unreachable: {exc}") from exc
        return resp.json().get("message", {}).get("content", "")


# ---------------------------------------------------------------------------
# Groq implementation
# ---------------------------------------------------------------------------

class GroqAgentPlanner:
    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.groq_api_key
        self._model = settings.groq_model
        self._base_url = settings.groq_base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    def set_client(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def generate_plan(
        self,
        goal: str,
        tool_schemas: list[dict[str, Any]],
        dataset_id: str | None,
        connection_id: str | None,
        conversation_history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        user_prompt = _build_user_prompt(
            goal, tool_schemas, dataset_id, connection_id, conversation_history
        )
        content = await self._chat(GROQ_SYSTEM_PROMPT, user_prompt)
        return _parse_response(content, "Groq")

    async def replan(
        self,
        goal: str,
        tool_schemas: list[dict[str, Any]],
        completed_results: list[dict[str, Any]],
        failed_step: dict[str, Any],
        error: str,
        remaining_steps: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        user_prompt = _build_replan_prompt(
            goal, completed_results, failed_step, error, remaining_steps, tool_schemas
        )
        content = await self._chat(_GROQ_REPLAN_SYSTEM_PROMPT, user_prompt)
        return _parse_replan(content, "Groq")

    async def _chat(self, system: str, user: str, temperature: float = 0.3) -> str:
        if not self._api_key:
            raise LLMError("GROQ_API_KEY is not set.")
        if self._client is None:
            raise LLMError("Agent LLM HTTP client not initialised.")
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        try:
            resp = await self._client.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError(f"Groq '{self._model}' unreachable: {exc}") from exc
        return (
            resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        )


# ---------------------------------------------------------------------------
# Fallback (tries primary; on LLMError uses secondary)
# ---------------------------------------------------------------------------

class FallbackAgentPlanner:
    def __init__(self, primary: Any, secondary: Any) -> None:
        self._primary = primary
        self._secondary = secondary

    def set_client(self, client: httpx.AsyncClient) -> None:
        for p in (self._primary, self._secondary):
            if hasattr(p, "set_client"):
                p.set_client(client)

    async def generate_plan(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            return await self._primary.generate_plan(*args, **kwargs)
        except LLMError as primary_exc:
            logger.warning("Primary agent planner failed (%s); trying secondary.", primary_exc)
            try:
                return await self._secondary.generate_plan(*args, **kwargs)
            except LLMError as secondary_exc:
                raise LLMError(
                    f"Both LLM providers failed. "
                    f"Primary: {primary_exc}. Secondary: {secondary_exc}"
                ) from secondary_exc

    async def replan(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        try:
            return await self._primary.replan(*args, **kwargs)
        except LLMError as primary_exc:
            logger.warning("Primary agent re-planner failed (%s); trying secondary.", primary_exc)
            try:
                return await self._secondary.replan(*args, **kwargs)
            except LLMError as secondary_exc:
                raise LLMError(
                    f"Both LLM providers failed. "
                    f"Primary: {primary_exc}. Secondary: {secondary_exc}"
                ) from secondary_exc
