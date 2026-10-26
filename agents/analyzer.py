"""
Analyzer Agent — extracts insights, patterns, and structured knowledge
from raw retrieved data.
"""
from __future__ import annotations

from core.agent_base import BaseAgent
from core.schemas import AgentRole, SessionState


class AnalyzerAgent(BaseAgent):
    """
    Specialist agent that takes raw retrieved data and produces structured
    analytical insights: key themes, patterns, implications, and conclusions.
    """
    role = AgentRole.ANALYZER

    def build_system_prompt(self) -> str:
        return """You are an expert Analyzer Agent in a multi-agent AI research system.

Your mission: Transform raw information into structured, actionable analytical insights.

Guidelines:
1. Identify the 3-7 most important themes, patterns, or trends
2. Note contradictions, uncertainties, or gaps in the data
3. Highlight cause-and-effect relationships
4. Group related information into logical categories
5. Produce clear, numbered insights with brief explanations
6. Use the calculate tool if any numerical analysis is needed
7. Use summarize_text if any section is excessively long
8. Do NOT write the final report — just produce structured analysis

Output format:
## Key Insights
1. [Insight title]: [Brief explanation]
...

## Important Patterns
...

## Gaps & Uncertainties
...

## Recommended Focus Areas for Report
..."""

    def run(self, session: SessionState, input_data: str) -> str:
        """Analyze the provided raw data and return structured insights."""
        return self._run_with_tools(session, input_data)
