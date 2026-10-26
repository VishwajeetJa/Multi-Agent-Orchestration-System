"""
Retriever Agent — gathers raw information, facts, and data.
Uses web search and URL fetch tools to ground responses in real data.
"""
from __future__ import annotations

from core.agent_base import BaseAgent
from core.schemas import AgentRole, SessionState

class RetrieverAgent(BaseAgent):
    """
    Specialist agent responsible for gathering comprehensive raw information
    on a topic using available tools (web search, URL fetch) and Gemini's
    own knowledge base.
    """
    role = AgentRole.RETRIEVER

    def build_system_prompt(self) -> str:
        return """You are a highly capable Retriever Agent in a multi-agent AI research system.

Your mission: Gather comprehensive, accurate, and detailed raw information on any given topic.

Guidelines:
1. Use the web_search tool to find current information
2. Use fetch_url if you need to read a specific article or page
3. Be thorough — cover multiple angles: definitions, examples, statistics, history, current state
4. Include sources where possible
5. Do NOT analyze or summarize — just gather the raw facts and data
6. If a tool returns an error, try a different search term or skip gracefully
7. Aim for 300-600 words of raw information

Always start by searching for the core topic, then search for related subtopics."""

    def run(self, session: SessionState, input_data: str) -> str:
        """Retrieve information for the given topic/query."""
        return self._run_with_tools(session, input_data)
