"""
Orchestrator — the "brain" of the multi-agent system.
Coordinates the Planner, specialist agents, and Critic in the right order.
"""
from __future__ import annotations
import logging
from datetime import datetime
from typing import Dict, Optional, Type

from core.schemas import (
    AgentRole, SessionState, SubTask, TaskPlan, TaskStatus, Priority
)
from core.memory import MemoryManager
from core.logging_config import bind_session, get_logger

logger = get_logger(__name__)


class Orchestrator:
    """
    Manages the full lifecycle of a workflow session:
    1. Accepts a user query
    2. Delegates planning to the Planner agent
    3. Routes subtasks to specialist agents
    4. Runs the Critic on final output
    5. Loops back for revision if quality is insufficient
    """

    # Lazy imports to avoid circular deps — agents register themselves
    _agent_registry: Dict[AgentRole, object] = {}

    def __init__(self, memory: MemoryManager, model_name: str = "gemini-1.5-flash"):
        self.memory = memory
        self.model_name = model_name
        self._setup_agents()

    def _setup_agents(self) -> None:
        """Instantiate all specialist agents and register them."""
        from agents.planner import PlannerAgent
        from agents.retriever import RetrieverAgent
        from agents.analyzer import AnalyzerAgent
        from agents.writer import WriterAgent
        from agents.critic import CriticAgent

        common_kwargs = {"model_name": self.model_name, "memory": self.memory}

        self._agents = {
            AgentRole.PLANNER:    PlannerAgent(**common_kwargs),
            AgentRole.RETRIEVER:  RetrieverAgent(**common_kwargs),
            AgentRole.ANALYZER:   AnalyzerAgent(**common_kwargs),
            AgentRole.WRITER:     WriterAgent(**common_kwargs),
            AgentRole.CRITIC:     CriticAgent(**common_kwargs),
        }
        logger.info("Orchestrator initialized with %d agents", len(self._agents))

    # ──────────────────────────── Public entry point ─────────────────────────

    def run_session(self, session: SessionState) -> str:
        """
        Execute a full workflow for the given session.
        Returns the final result string.
        """
        bind_session(session.session_id)
        logger.info("Starting workflow", query=session.user_query[:100])

        try:
            session.status = TaskStatus.IN_PROGRESS
            self.memory.save_session(session)

            # ── Step 1: Plan the workflow ──────────────────────────────────
            logger.info("Phase 1: Planning")
            planner = self._agents[AgentRole.PLANNER]
            plan = planner.run(session, session.user_query)
            session.plan = plan
            self.memory.save_session(session)

            # ── Step 2: Execute subtasks in dependency order ───────────────
            logger.info("Phase 2: Executing subtasks", count=len(plan.subtasks))
            context_accumulator: Dict[str, str] = {}  # task_id → output

            max_rounds = len(plan.subtasks) * 2  # Safety cap
            rounds = 0
            while True:
                ready_tasks = plan.get_next_ready_tasks()
                if not ready_tasks:
                    break
                if rounds >= max_rounds:
                    logger.warning("Max scheduling rounds reached — breaking loop")
                    break
                rounds += 1

                for subtask in ready_tasks:
                    self._execute_subtask(subtask, session, context_accumulator, plan)

            # ── Step 3: Gather the Writer's output ────────────────────────
            writer_output = self._get_writer_output(plan, context_accumulator)

            # ── Step 4: Critic evaluation (up to 2 revision cycles) ───────
            logger.info("Phase 3: Critic evaluation")
            final_result = self._critic_loop(
                session, writer_output, session.user_query, max_revisions=2
            )

            # ── Step 5: Persist final result ──────────────────────────────
            self.memory.set_final_result(session.session_id, final_result)
            logger.info("Workflow completed successfully")
            return final_result

        except Exception as exc:
            logger.error("Workflow failed", error=str(exc), exc_info=True)
            self.memory.set_session_error(session.session_id, str(exc))
            raise

    # ──────────────────────────── Internal helpers ───────────────────────────

    def _execute_subtask(
        self,
        subtask: SubTask,
        session: SessionState,
        context: Dict[str, str],
        plan: TaskPlan,
    ) -> None:
        """Run a single subtask using the appropriate specialist agent."""
        agent = self._agents.get(subtask.assigned_to)
        if not agent:
            subtask.status = TaskStatus.FAILED
            subtask.error_message = f"No agent registered for role '{subtask.assigned_to}'"
            return

        # Build input: subtask description + outputs of dependencies
        dep_context = "\n\n".join(
            f"[{dep_id}] {context.get(dep_id, '(no output)')}"
            for dep_id in subtask.dependencies
        )
        full_input = subtask.description
        if dep_context:
            full_input = f"Previous context:\n{dep_context}\n\nYour task:\n{subtask.description}"

        subtask.status = TaskStatus.IN_PROGRESS
        subtask.started_at = datetime.utcnow()
        subtask.input_data = full_input[:500]

        logger.info(
            "Executing subtask",
            agent=subtask.assigned_to,
            task_title=subtask.title,
        )

        try:
            output = agent.run(session, full_input)
            subtask.output_data = output
            subtask.status = TaskStatus.COMPLETED
            subtask.completed_at = datetime.utcnow()
            context[subtask.task_id] = output
        except Exception as exc:
            subtask.status = TaskStatus.FAILED
            subtask.error_message = str(exc)
            subtask.completed_at = datetime.utcnow()
            context[subtask.task_id] = f"[FAILED: {exc}]"
            logger.error("Subtask failed", task=subtask.title, error=str(exc))

    def _get_writer_output(
        self, plan: TaskPlan, context: Dict[str, str]
    ) -> str:
        """Find and return the output of the Writer subtask(s)."""
        for subtask in reversed(plan.subtasks):
            if subtask.assigned_to == AgentRole.WRITER and subtask.output_data:
                return subtask.output_data
        # Fall back to the last completed subtask
        for subtask in reversed(plan.subtasks):
            if subtask.status == TaskStatus.COMPLETED and subtask.output_data:
                return subtask.output_data
        return "No output was produced."

    def _critic_loop(
        self,
        session: SessionState,
        draft: str,
        original_query: str,
        max_revisions: int = 2,
    ) -> str:
        """
        Run the Critic on a draft. If it fails, run the Writer again
        with revision instructions. Repeat up to max_revisions times.
        """
        critic = self._agents[AgentRole.CRITIC]
        writer = self._agents[AgentRole.WRITER]
        current_draft = draft

        for revision_num in range(max_revisions + 1):
            feedback = critic.evaluate(session, current_draft, original_query)

            if feedback.passed:
                logger.info(
                    "Critic approved output",
                    score=feedback.quality_score,
                    revision=revision_num,
                )
                return current_draft

            if revision_num < max_revisions:
                logger.info(
                    "Critic requested revision",
                    score=feedback.quality_score,
                    revision=revision_num + 1,
                )
                revision_prompt = (
                    f"The following draft scored {feedback.quality_score}/10.\n"
                    f"Weaknesses: {'; '.join(feedback.weaknesses)}\n\n"
                    f"Revision instructions: {feedback.revision_instructions}\n\n"
                    f"Original draft:\n{current_draft}\n\n"
                    f"Please revise and improve the draft to address the feedback."
                )
                current_draft = writer.run(session, revision_prompt)

        logger.warning("Critic max revisions reached — returning best available draft")
        return current_draft
