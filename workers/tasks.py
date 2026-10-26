"""
Celery tasks — thin wrappers that delegate to the Orchestrator.
"""
from __future__ import annotations
import logging
import os

from celery import Task
from dotenv import load_dotenv
import google.genai as genai

from workers.celery_app import celery_app
from core.memory import MemoryManager
from core.orchestrator import Orchestrator
from core.schemas import SessionState, TaskStatus
from core.logging_config import configure_logging, bind_session

load_dotenv()
configure_logging()

logger = logging.getLogger(__name__)

# Configure Gemini once at module load
_genai_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY", ""))

# Shared instances (created once per worker process)
_memory: MemoryManager | None = None
_orchestrator: Orchestrator | None = None


def _get_memory() -> MemoryManager:
    global _memory
    if _memory is None:
        _memory = MemoryManager(os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"))
    return _memory


def _get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator(memory=_get_memory())
    return _orchestrator


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    name="workers.tasks.run_workflow_task",
    track_started=True,
)
def run_workflow_task(self: Task, session_id: str) -> dict:
    """
    Main Celery task: retrieves the session from Redis and runs the full
    orchestration workflow. Returns a dict with the final result.
    """
    bind_session(session_id)
    memory = _get_memory()
    orchestrator = _get_orchestrator()

    session = memory.get_session(session_id)
    if session is None:
        raise ValueError(f"Session {session_id} not found in memory")

    try:
        logger.info("Celery task starting for session %s", session_id)
        self.update_state(state="IN_PROGRESS", meta={"session_id": session_id, "status": "running"})

        result = orchestrator.run_session(session)

        return {
            "session_id": session_id,
            "status": "completed",
            "result": result,
        }
    except Exception as exc:
        logger.error("Workflow task failed for session %s: %s", session_id, exc, exc_info=True)
        memory.set_session_error(session_id, str(exc))
        raise self.retry(exc=exc, countdown=10)
