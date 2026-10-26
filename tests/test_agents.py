"""
Unit tests for all specialist agents.
Run with: pytest tests/ -v
"""
import pytest
from unittest.mock import MagicMock, patch
from core.schemas import AgentRole, SessionState, TaskStatus, Priority


def make_session(query="Test query"):
    return SessionState(user_query=query, status=TaskStatus.PENDING)


# ── PlannerAgent tests ───────────────────────────────────────────
class TestPlannerAgent:
    def test_default_plan_has_three_steps(self):
        from agents.planner import PlannerAgent
        planner = PlannerAgent.__new__(PlannerAgent)
        session = make_session()
        plan = planner._default_plan(session, "Tell me about AI")
        assert len(plan.subtasks) == 3
        roles = [t.assigned_to for t in plan.subtasks]
        assert AgentRole.RETRIEVER in roles
        assert AgentRole.ANALYZER in roles
        assert AgentRole.WRITER in roles

    def test_default_plan_has_correct_dependencies(self):
        from agents.planner import PlannerAgent
        planner = PlannerAgent.__new__(PlannerAgent)
        session = make_session()
        plan = planner._default_plan(session, "test")
        retriever_id = plan.subtasks[0].task_id
        analyzer_id  = plan.subtasks[1].task_id
        assert retriever_id in plan.subtasks[1].dependencies
        assert analyzer_id  in plan.subtasks[2].dependencies

    def test_parse_plan_valid_json(self):
        from agents.planner import PlannerAgent
        planner = PlannerAgent.__new__(PlannerAgent)
        session = make_session()
        raw_json = '''{
          "subtasks": [
            {"title": "Gather data", "description": "Search for info", "assigned_to": "retriever", "priority": "high", "depends_on_indices": []},
            {"title": "Analyze", "description": "Find patterns", "assigned_to": "analyzer", "priority": "medium", "depends_on_indices": [0]},
            {"title": "Write", "description": "Write report", "assigned_to": "writer", "priority": "medium", "depends_on_indices": [1]}
          ]
        }'''
        plan = planner._parse_plan(session, "test query", raw_json)
        assert len(plan.subtasks) == 3
        assert plan.subtasks[1].dependencies == [plan.subtasks[0].task_id]

    def test_parse_plan_invalid_json_falls_back(self):
        from agents.planner import PlannerAgent
        planner = PlannerAgent.__new__(PlannerAgent)
        session = make_session()
        plan = planner._parse_plan(session, "test", "not json at all !!!")
        assert len(plan.subtasks) == 3  # Default plan


# ── CriticAgent tests ────────────────────────────────────────────
class TestCriticAgent:
    def test_parse_feedback_passing_score(self):
        from agents.critic import CriticAgent
        critic = CriticAgent.__new__(CriticAgent)
        raw = '{"quality_score": 8.5, "passed": true, "strengths": ["clear"], "weaknesses": [], "revision_instructions": null}'
        feedback = critic._parse_feedback("session-123", raw)
        assert feedback.passed is True
        assert feedback.quality_score == 8.5
        assert "clear" in feedback.strengths

    def test_parse_feedback_failing_score(self):
        from agents.critic import CriticAgent
        critic = CriticAgent.__new__(CriticAgent)
        raw = '{"quality_score": 4.0, "passed": false, "strengths": [], "weaknesses": ["too short"], "revision_instructions": "Add more detail"}'
        feedback = critic._parse_feedback("session-123", raw)
        assert feedback.passed is False
        assert feedback.revision_instructions == "Add more detail"

    def test_parse_feedback_no_json_defaults_to_pass(self):
        from agents.critic import CriticAgent
        critic = CriticAgent.__new__(CriticAgent)
        feedback = critic._parse_feedback("session-123", "no json here")
        assert feedback.passed is True


# ── Schemas tests ────────────────────────────────────────────────
class TestSchemas:
    def test_task_plan_get_next_ready_tasks(self):
        from core.schemas import SubTask, TaskPlan
        session = make_session()
        t1 = SubTask(session_id=session.session_id, title="A", description="", assigned_to=AgentRole.RETRIEVER)
        t2 = SubTask(session_id=session.session_id, title="B", description="", assigned_to=AgentRole.ANALYZER, dependencies=[t1.task_id])
        t3 = SubTask(session_id=session.session_id, title="C", description="", assigned_to=AgentRole.WRITER, dependencies=[t2.task_id])
        plan = TaskPlan(session_id=session.session_id, original_query="test", subtasks=[t1, t2, t3])

        ready = plan.get_next_ready_tasks()
        assert len(ready) == 1
        assert ready[0].task_id == t1.task_id

        # Mark t1 as done
        t1.status = TaskStatus.COMPLETED
        ready2 = plan.get_next_ready_tasks()
        assert len(ready2) == 1
        assert ready2[0].task_id == t2.task_id

    def test_session_state_serialization(self):
        session = make_session("Hello world")
        json_str = session.model_dump_json()
        restored = SessionState.model_validate_json(json_str)
        assert restored.user_query == "Hello world"
        assert restored.status == TaskStatus.PENDING


# ── MemoryManager tests ──────────────────────────────────────────
class TestMemoryManager:
    @pytest.fixture
    def memory(self):
        """Create a MemoryManager with a mock Redis client."""
        from core.memory import MemoryManager
        mem = MemoryManager.__new__(MemoryManager)
        mem._client = MagicMock()
        return mem

    def test_save_and_get_session(self, memory):
        session = make_session("Test query")
        session_json = session.model_dump_json()

        memory._client.setex = MagicMock()
        memory._client.get = MagicMock(return_value=session_json)

        memory.save_session(session)
        memory._client.setex.assert_called_once()

        retrieved = memory.get_session(session.session_id)
        assert retrieved is not None
        assert retrieved.user_query == "Test query"

    def test_get_session_not_found(self, memory):
        memory._client.get = MagicMock(return_value=None)
        result = memory.get_session("nonexistent-id")
        assert result is None

    def test_ping(self, memory):
        memory._client.ping = MagicMock(return_value=True)
        assert memory.ping() is True

        memory._client.ping = MagicMock(side_effect=Exception("connection refused"))
        assert memory.ping() is False
