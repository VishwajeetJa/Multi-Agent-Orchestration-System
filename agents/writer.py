"""
Writer Agent — synthesizes analysis into a polished, professional final document.
"""
from __future__ import annotations

from core.agent_base import BaseAgent
from core.schemas import AgentRole, SessionState


class WriterAgent(BaseAgent):
    """
    Specialist agent that produces the final professional report
    from analytical insights.
    """
    role = AgentRole.WRITER

    def build_system_prompt(self) -> str:
        return """You are an elite Writer Agent in a multi-agent AI research system.

Your mission: Transform analytical insights into a compelling, polished, professional report.

Guidelines:
1. Write in a clear, authoritative, and engaging tone
2. Use proper structure: Executive Summary → Main Body → Conclusions → Recommendations
3. Every section must have a clear heading
4. Support claims with evidence from the analysis
5. Use bullet points for lists, numbered steps for processes
6. Keep language accessible but professional
7. End with 3-5 actionable recommendations
8. Aim for 400-800 words unless the topic demands more
9. Use the get_datetime tool to timestamp the report

Report structure:
# [Report Title]
**Generated:** [timestamp]
**Query:** [original query]

## Executive Summary
...

## [Key Section 1]
...

## [Key Section 2]
...

## Conclusions
...

## Recommendations
1. ...
2. ...
..."""

    def run(self, session: SessionState, input_data: str) -> str:
        """Write a professional report from the provided analysis."""
        return self._run_with_tools(session, input_data)
