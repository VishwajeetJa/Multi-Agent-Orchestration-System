"""
Pydantic schemas for structured inter-agent communication.
All data flowing between agents is validated against these models.
"""
from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
import uuid


class AgentRole(str, Enum):
    PLANNER = "planner"
    RETRIEVER = "retriever"
    ANALYZER = "analyzer"
    WRITER = "writer"
    CRITIC = "critic"
    ORCHESTRATOR = "orchestrator"


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    NEEDS_REVISION = "needs_revision"


class Priority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ToolCall(BaseModel):
    """Represents a tool invocation by an agent."""
    tool_name: str
    arguments: Dict[str, Any]
    result: Optional[str] = None
    error: Optional[str] = None
    executed_at: Optional[datetime] = None


class AgentMessage(BaseModel):
    """Structured message passed between agents."""
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    from_agent: AgentRole
    to_agent: Optional[AgentRole] = None
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    tool_calls: List[ToolCall] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SubTask(BaseModel):
    """A single unit of work assigned to one agent."""
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    title: str
    description: str
    assigned_to: AgentRole
    priority: Priority = Priority.MEDIUM
    dependencies: List[str] = Field(default_factory=list)   # task_ids this depends on
    status: TaskStatus = TaskStatus.PENDING
    input_data: Optional[str] = None
    output_data: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @property
    def duration_seconds(self) -> Optional[float]:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


class TaskPlan(BaseModel):
    """The orchestrated plan produced by the Planner agent."""
    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    original_query: str
    subtasks: List[SubTask]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def get_next_ready_tasks(self) -> List[SubTask]:
        """Returns tasks whose dependencies are all completed."""
        completed_ids = {t.task_id for t in self.subtasks if t.status == TaskStatus.COMPLETED}
        return [
            t for t in self.subtasks
            if t.status == TaskStatus.PENDING
            and all(dep in completed_ids for dep in t.dependencies)
        ]


class CriticFeedback(BaseModel):
    """Structured feedback from the Critic agent."""
    feedback_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str
    quality_score: float = Field(ge=0.0, le=10.0)
    passed: bool
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    revision_instructions: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SessionState(BaseModel):
    """Full state of one orchestration session."""
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_query: str
    status: TaskStatus = TaskStatus.PENDING
    plan: Optional[TaskPlan] = None
    messages: List[AgentMessage] = Field(default_factory=list)
    final_result: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict()


class WorkflowRequest(BaseModel):
    """Incoming API request to start a workflow."""
    query: str = Field(..., min_length=1, max_length=10000, description="The task to perform")
    priority: Priority = Priority.MEDIUM
    context: Optional[str] = None  # Optional extra context


class WorkflowResponse(BaseModel):
    """API response after accepting a workflow request."""
    session_id: str
    status: TaskStatus
    message: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
