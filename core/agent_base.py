"""
Base Agent class — all specialized agents inherit from this.
Handles tool parsing, Gemini communication (via google.genai), retry logic,
and message logging.
"""
from __future__ import annotations
import json
import re
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import List, Optional

import google.genai as genai
from google.genai import types as genai_types
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from core.schemas import AgentMessage, AgentRole, SessionState, ToolCall
from core.tools import ToolRegistry, tool_registry
from core.memory import MemoryManager

logger = logging.getLogger(__name__)

# Pattern to detect tool call blocks in model output
TOOL_CALL_PATTERN = re.compile(r"```tool_call\s*\n(.*?)\n```", re.DOTALL)


class BaseAgent(ABC):
    """
    Abstract base for all agents. Provides:
    - google.genai (new SDK) communication with retry
    - ReAct tool-use loop (plan → call tool → observe → repeat)
    - Tool call parsing and execution
    - Memory / message persistence
    - Structured logging
    """

    role: AgentRole  # Must be set by subclasses

    def __init__(
        self,
        model_name: str = "gemini-2.0-flash",
        tools: Optional[ToolRegistry] = None,
        memory: Optional[MemoryManager] = None,
        max_tool_iterations: int = 5,
        api_key: Optional[str] = None,
    ):
        import os
        _api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self._client = genai.Client(api_key=_api_key)
        self.model_name = model_name
        self.tools = tools or tool_registry
        self.memory = memory
        self.max_tool_iterations = max_tool_iterations

    @abstractmethod
    def build_system_prompt(self) -> str:
        """Return the system prompt that defines this agent's persona and instructions."""

    @abstractmethod
    def run(self, session: SessionState, input_data: str) -> str:
        """Execute this agent's task and return its output."""

    # ──────────────────────────── Gemini communication ──────────────────────

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def _call_llm(self, prompt: str) -> str:
        """Call Gemini via the new google.genai SDK with automatic retry."""
        response = self._client.models.generate_content(
            model=self.model_name,
            contents=prompt,
        )
        return response.text or ""

    def _run_with_tools(self, session: SessionState, initial_prompt: str) -> str:
        """
        ReAct-style agent loop:
        1. Call LLM → 2. Parse tool calls → 3. Execute tools → 4. Feed results back → repeat.
        """
        system = self.build_system_prompt()
        tools_block = self.tools.to_system_prompt_block()
        conversation = [f"{system}\n\n{tools_block}\n\nUser request:\n{initial_prompt}"]
        collected_tool_calls: List[ToolCall] = []

        for iteration in range(self.max_tool_iterations):
            full_prompt = "\n\n---\n\n".join(conversation)
            raw_response = self._call_llm(full_prompt)

            # Check if the model wants to use a tool
            tool_matches = TOOL_CALL_PATTERN.findall(raw_response)
            if not tool_matches:
                # No more tool calls — final answer
                self._log_message(session, raw_response, collected_tool_calls)
                return self._strip_tool_blocks(raw_response)

            # Execute each tool call found in the response
            tool_results_block = []
            for match in tool_matches:
                try:
                    call_data = json.loads(match.strip())
                    tool_name = call_data.get("tool", "")
                    args = call_data.get("args", {})
                    result = self.tools.run(tool_name, **args)

                    tc = ToolCall(
                        tool_name=tool_name,
                        arguments=args,
                        result=result,
                        executed_at=datetime.now(timezone.utc),
                    )
                    collected_tool_calls.append(tc)
                    tool_results_block.append(f"Tool '{tool_name}' result:\n{result}")
                    logger.debug("Agent %s ran tool '%s' → %s chars", self.role, tool_name, len(result))
                except json.JSONDecodeError as e:
                    tool_results_block.append(f"[Tool parse error]: {e}")

            # Feed tool results back into the conversation
            conversation.append(raw_response)
            conversation.append("\n".join(tool_results_block))
            conversation.append("Continue your analysis using the tool results above.")

        # Max iterations reached — return whatever we have
        logger.warning("Agent %s hit max tool iterations (%d)", self.role, self.max_tool_iterations)
        final = self._call_llm(
            "\n\n---\n\n".join(conversation) + "\n\nProvide your final answer now."
        )
        self._log_message(session, final, collected_tool_calls)
        return self._strip_tool_blocks(final)

    # ──────────────────────────── Helpers ───────────────────────────────────

    def _log_message(
        self,
        session: SessionState,
        content: str,
        tool_calls: Optional[List[ToolCall]] = None,
    ) -> None:
        """Persist an agent message to session memory."""
        if not self.memory:
            return
        msg = AgentMessage(
            session_id=session.session_id,
            from_agent=self.role,
            content=content[:2000],  # Truncate for storage
            tool_calls=tool_calls or [],
        )
        self.memory.append_message(session.session_id, msg)

    @staticmethod
    def _strip_tool_blocks(text: str) -> str:
        """Remove raw tool_call JSON blocks from the final response."""
        return TOOL_CALL_PATTERN.sub("", text).strip()
