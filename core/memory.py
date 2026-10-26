"""
Shared memory layer for the multi-agent system.
Provides session state persistence via Redis and conversation history management.
"""
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional
import redis
from core.schemas import SessionState, AgentMessage, TaskStatus

logger = logging.getLogger(__name__)

# TTL for session state in Redis (24 hours)
SESSION_TTL_SECONDS = 86400


class MemoryManager:
    """
    Centralized memory store for all agent sessions.
    Backed by Redis for persistence and fast access.
    """

    def __init__(self, redis_url: str):
        self._client = redis.from_url(redis_url, decode_responses=True)
        logger.info("MemoryManager connected to Redis at %s", redis_url)

    # ──────────────────────────── Session CRUD ──────────────────────────────

    def save_session(self, session: SessionState) -> None:
        """Persist the full session state to Redis."""
        session.updated_at = datetime.now(timezone.utc)
        key = self._session_key(session.session_id)
        self._client.setex(key, SESSION_TTL_SECONDS, session.model_dump_json())
        logger.debug("Saved session %s (status=%s)", session.session_id, session.status)

    def get_session(self, session_id: str) -> Optional[SessionState]:
        """Retrieve a session by ID; returns None if not found."""
        raw = self._client.get(self._session_key(session_id))
        if not raw:
            return None
        try:
            return SessionState.model_validate_json(raw)
        except Exception as exc:
            logger.error("Failed to deserialize session %s: %s", session_id, exc)
            return None

    def delete_session(self, session_id: str) -> bool:
        """Delete a session from memory."""
        return bool(self._client.delete(self._session_key(session_id)))

    def list_active_sessions(self) -> List[str]:
        """Return all active session IDs."""
        keys = self._client.keys("session:*")
        return [k.replace("session:", "") for k in keys]

    # ──────────────────────────── Messages ──────────────────────────────────

    def append_message(self, session_id: str, message: AgentMessage) -> None:
        """Add a message to the session's conversation history."""
        session = self.get_session(session_id)
        if session is None:
            logger.warning("Cannot append message — session %s not found", session_id)
            return
        session.messages.append(message)
        self.save_session(session)

    def get_conversation_history(self, session_id: str, last_n: int = 20) -> List[AgentMessage]:
        """Retrieve the last N messages for a session."""
        session = self.get_session(session_id)
        if session is None:
            return []
        return session.messages[-last_n:]

    # ──────────────────────────── Status helpers ─────────────────────────────

    def update_session_status(self, session_id: str, status: TaskStatus) -> None:
        """Update only the status field of a session."""
        session = self.get_session(session_id)
        if session:
            session.status = status
            self.save_session(session)

    def set_final_result(self, session_id: str, result: str) -> None:
        """Store the final result and mark session as completed."""
        session = self.get_session(session_id)
        if session:
            session.final_result = result
            session.status = TaskStatus.COMPLETED
            self.save_session(session)

    def set_session_error(self, session_id: str, error: str) -> None:
        """Record an error and mark session as failed."""
        session = self.get_session(session_id)
        if session:
            session.error = error
            session.status = TaskStatus.FAILED
            self.save_session(session)

    # ──────────────────────────── Rate limiting ──────────────────────────────

    def check_rate_limit(self, identifier: str, limit: int, window_seconds: int) -> bool:
        """
        Token-bucket rate limiter.
        Returns True if the request is allowed, False if limit exceeded.
        """
        key = f"rate:{identifier}"
        pipe = self._client.pipeline()
        now = datetime.utcnow().timestamp()
        window_start = now - window_seconds

        pipe.zremrangebyscore(key, "-inf", window_start)
        pipe.zadd(key, {str(now): now})
        pipe.zcard(key)
        pipe.expire(key, window_seconds)
        results = pipe.execute()

        count = results[2]
        return count <= limit

    # ──────────────────────────── Internal helpers ───────────────────────────

    @staticmethod
    def _session_key(session_id: str) -> str:
        return f"session:{session_id}"

    def ping(self) -> bool:
        """Health check — returns True if Redis is reachable."""
        try:
            return self._client.ping()
        except Exception:
            return False
