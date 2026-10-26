"""
Planner Agent — decomposes a user query into an executable task DAG.
Uses Gemini to generate a structured plan with subtasks and dependencies.
"""
from __future__ import annotations
import json
import logging
import re
from typing import List

from core.agent_base import BaseAgent
from core.schemas import AgentRole, SessionState, SubTask, TaskPlan, Priority

logger = logging.getLogger(__name__)


class PlannerAgent(BaseAgent):
    """
    Analyzes a user query and produces a TaskPlan — a directed list of
    subtasks with assigned agents and dependency relationships.
    """
    role = AgentRole.PLANNER

    def build_system_prompt(self) -> str:
        return """You are a strategic Planner Agent in a multi-agent AI system.
Your job is to analyze a user's request and break it into a clear, ordered list of subtasks.

Available agents you can assign tasks to:
- retriever: Gathers raw information, facts, and data about a topic
- analyzer: Identifies key patterns, insights, and themes from gathered data
- writer: Synthesizes insights into a polished, professional final document

Rules:
1. Always start with at least one retriever task
2. analyzer tasks depend on retriever output
3. writer tasks depend on analyzer output
4. Keep subtask descriptions specific and actionable
5. Return ONLY valid JSON — no extra text

Output format:
{
  "subtasks": [
    {
      "title": "Short title",
      "description": "Detailed description of what this agent should do",
      "assigned_to": "retriever|analyzer|writer",
      "priority": "high|medium|low",
      "depends_on_indices": []
    }
  ]
}

depends_on_indices: list of 0-based indices of tasks this task depends on (empty = no dependencies).
"""

    def run(self, session: SessionState, input_data: str) -> TaskPlan:
        """Generate a TaskPlan from the user query."""
        prompt = (
            f"{self.build_system_prompt()}\n\n"
            f"User query to plan:\n{input_data}\n\n"
            "Generate the task plan as JSON:"
        )

        raw = self._call_llm(prompt)
        self._log_message(session, raw)
        return self._parse_plan(session, input_data, raw)

    def _parse_plan(self, session: SessionState, query: str, raw: str) -> TaskPlan:
        """Parse the LLM JSON output into a TaskPlan with linked task IDs."""
        # Extract JSON from the response
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not json_match:
            logger.warning("Planner returned no JSON — using default plan")
            return self._default_plan(session, query)

        try:
            data = json.loads(json_match.group())
            raw_tasks = data.get("subtasks", [])
        except json.JSONDecodeError as e:
            logger.error("Failed to parse plan JSON: %s", e)
            return self._default_plan(session, query)

        # First pass: create SubTask objects (without dependency links yet)
        subtasks: List[SubTask] = []
        for i, raw_task in enumerate(raw_tasks):
            role_str = raw_task.get("assigned_to", "retriever")
            try:
                role = AgentRole(role_str)
            except ValueError:
                role = AgentRole.RETRIEVER

            priority_str = raw_task.get("priority", "medium")
            try:
                priority = Priority(priority_str)
            except ValueError:
                priority = Priority.MEDIUM

            subtasks.append(SubTask(
                session_id=session.session_id,
                title=raw_task.get("title", f"Task {i+1}"),
                description=raw_task.get("description", ""),
                assigned_to=role,
                priority=priority,
            ))

        # Second pass: wire up dependencies by index
        for i, raw_task in enumerate(raw_tasks):
            dep_indices = raw_task.get("depends_on_indices", [])
            for dep_idx in dep_indices:
                if 0 <= dep_idx < len(subtasks) and dep_idx != i:
                    subtasks[i].dependencies.append(subtasks[dep_idx].task_id)

        plan = TaskPlan(
            session_id=session.session_id,
            original_query=query,
            subtasks=subtasks,
        )
        logger.info("Plan created: %d subtasks", len(subtasks))
        return plan

    def _default_plan(self, session: SessionState, query: str) -> TaskPlan:
        """Fallback 3-step linear plan when JSON parsing fails."""
        retriever = SubTask(
            session_id=session.session_id,
            title="Retrieve Information",
            description=f"Gather comprehensive information about: {query}",
            assigned_to=AgentRole.RETRIEVER,
            priority=Priority.HIGH,
        )
        analyzer = SubTask(
            session_id=session.session_id,
            title="Analyze Data",
            description="Analyze the retrieved information and identify key insights.",
            assigned_to=AgentRole.ANALYZER,
            priority=Priority.HIGH,
            dependencies=[retriever.task_id],
        )
        writer = SubTask(
            session_id=session.session_id,
            title="Write Report",
            description="Synthesize the analysis into a professional final report.",
            assigned_to=AgentRole.WRITER,
            priority=Priority.HIGH,
            dependencies=[analyzer.task_id],
        )
        return TaskPlan(
            session_id=session.session_id,
            original_query=query,
            subtasks=[retriever, analyzer, writer],
        )
