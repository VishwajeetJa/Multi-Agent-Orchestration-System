"""
Flask API routes — all endpoints for the multi-agent orchestration system.
"""
from __future__ import annotations
import json
import logging
import os
import time
from datetime import datetime

from flask import Blueprint, Response, jsonify, request, stream_with_context
from api.auth import require_auth, create_token
from core.memory import MemoryManager
from core.schemas import SessionState, TaskStatus, WorkflowRequest, Priority
from workers.tasks import run_workflow_task

logger = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__, url_prefix="/api/v1")

# ─── Dependency injection: memory is set by the app factory ──────────────────
_memory: MemoryManager | None = None


def set_memory(memory: MemoryManager) -> None:
    global _memory
    _memory = memory


def get_memory() -> MemoryManager:
    assert _memory is not None, "Memory not initialized — call set_memory() first"
    return _memory


# ─────────────────────────────── Auth routes ─────────────────────────────────

@api_bp.route("/token", methods=["POST"])
def get_token():
    """Issue a JWT token. Body: {user_id: str, secret: str}"""
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id", "anonymous")
    # Simple shared secret for demo — replace with real user DB in production
    provided_secret = data.get("secret", "")
    expected_secret = os.getenv("AUTH_SECRET", "change-me-in-production")

    if provided_secret != expected_secret:
        return jsonify({"error": "Invalid credentials"}), 401

    token = create_token(user_id)
    return jsonify({"token": token, "expires_in": "24h"})


# ─────────────────────────────── Workflow routes ──────────────────────────────

@api_bp.route("/workflow", methods=["POST"])
@require_auth
def start_workflow():
    """
    Start a new orchestration workflow.
    Body: {"query": "...", "priority": "high|medium|low", "context": "..."}
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400

    try:
        req = WorkflowRequest(**data)
    except Exception as e:
        return jsonify({"error": f"Invalid request: {e}"}), 422

    # Rate limiting: max 10 requests per minute per user
    memory = get_memory()
    user_id = getattr(request, "user_id", request.remote_addr)
    if not memory.check_rate_limit(f"workflow:{user_id}", limit=10, window_seconds=60):
        return jsonify({"error": "Rate limit exceeded — max 10 requests per minute"}), 429

    # Create session
    session = SessionState(
        user_query=req.query,
        status=TaskStatus.PENDING,
    )
    memory.save_session(session)

    # Determine Celery queue from priority
    queue_map = {Priority.HIGH: "high", Priority.MEDIUM: "medium", Priority.LOW: "low"}
    queue = queue_map.get(req.priority, "medium")

    # Dispatch Celery task
    celery_task = run_workflow_task.apply_async(
        args=[session.session_id],
        queue=queue,
    )

    logger.info("Workflow started: session=%s, celery_task=%s", session.session_id, celery_task.id)

    return jsonify({
        "session_id": session.session_id,
        "celery_task_id": celery_task.id,
        "status": "accepted",
        "message": "Workflow started. Poll /status or use /stream for live updates.",
    }), 202


@api_bp.route("/workflow/<session_id>/status", methods=["GET"])
@require_auth
def get_workflow_status(session_id: str):
    """Poll the current status of a workflow session."""
    session = get_memory().get_session(session_id)
    if not session:
        return jsonify({"error": f"Session '{session_id}' not found"}), 404

    response = {
        "session_id": session_id,
        "status": session.status,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
        "query": session.user_query,
    }

    if session.status == TaskStatus.COMPLETED:
        response["result"] = session.final_result
        if session.plan:
            response["plan_summary"] = {
                "total_subtasks": len(session.plan.subtasks),
                "completed": sum(1 for t in session.plan.subtasks if t.status == TaskStatus.COMPLETED),
                "failed": sum(1 for t in session.plan.subtasks if t.status == TaskStatus.FAILED),
            }

    if session.status == TaskStatus.FAILED:
        response["error"] = session.error

    return jsonify(response)


@api_bp.route("/workflow/<session_id>/stream", methods=["GET"])
@require_auth
def stream_workflow(session_id: str):
    """
    Server-Sent Events (SSE) endpoint for real-time workflow progress.
    Client receives status updates as the workflow progresses.
    """
    memory = get_memory()

    def event_generator():
        last_status = None
        last_msg_count = 0
        timeout = 300  # 5-minute max stream
        start = time.time()

        while time.time() - start < timeout:
            session = memory.get_session(session_id)
            if not session:
                yield f"data: {json.dumps({'error': 'Session not found'})}\n\n"
                break

            # Send status change events
            current_status = session.status
            if current_status != last_status:
                yield f"data: {json.dumps({'type': 'status', 'status': current_status})}\n\n"
                last_status = current_status

            # Send new messages as they arrive
            msgs = session.messages
            new_msgs = msgs[last_msg_count:]
            for msg in new_msgs:
                payload = {
                    "type": "agent_message",
                    "agent": msg.from_agent,
                    "preview": msg.content[:200],
                    "tool_calls": len(msg.tool_calls),
                    "timestamp": msg.created_at.isoformat(),
                }
                yield f"data: {json.dumps(payload)}\n\n"
            last_msg_count = len(msgs)

            # Send plan progress if available
            if session.plan:
                subtask_updates = []
                for t in session.plan.subtasks:
                    subtask_updates.append({
                        "title": t.title,
                        "agent": t.assigned_to,
                        "status": t.status,
                    })
                yield f"data: {json.dumps({'type': 'plan_progress', 'subtasks': subtask_updates})}\n\n"

            # Terminal state
            if current_status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                final_data = {"type": "done", "status": current_status}
                if session.final_result:
                    final_data["result"] = session.final_result
                if session.error:
                    final_data["error"] = session.error
                yield f"data: {json.dumps(final_data)}\n\n"
                break

            time.sleep(2)

        yield "data: {\"type\": \"stream_closed\"}\n\n"

    return Response(
        stream_with_context(event_generator()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@api_bp.route("/workflow/<session_id>/messages", methods=["GET"])
@require_auth
def get_messages(session_id: str):
    """Return all agent messages for a session (conversation history)."""
    memory = get_memory()
    msgs = memory.get_conversation_history(session_id, last_n=50)
    return jsonify({
        "session_id": session_id,
        "count": len(msgs),
        "messages": [
            {
                "from": m.from_agent,
                "content": m.content[:500],
                "tool_calls": len(m.tool_calls),
                "timestamp": m.created_at.isoformat(),
            }
            for m in msgs
        ],
    })


@api_bp.route("/sessions", methods=["GET"])
@require_auth
def list_sessions():
    """List all active session IDs."""
    memory = get_memory()
    session_ids = memory.list_active_sessions()
    sessions = []
    for sid in session_ids[:50]:  # Limit to 50
        s = memory.get_session(sid)
        if s:
            sessions.append({
                "session_id": sid,
                "status": s.status,
                "query": s.user_query[:80],
                "created_at": s.created_at.isoformat(),
            })
    return jsonify({"total": len(sessions), "sessions": sessions})


# ─────────────────────────────── Health & meta ───────────────────────────────

@api_bp.route("/health", methods=["GET"])
def health_check():
    """System health check — no auth required."""
    memory = get_memory()
    redis_ok = memory.ping()
    return jsonify({
        "status": "healthy" if redis_ok else "degraded",
        "redis": "connected" if redis_ok else "unreachable",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "2.0.0",
    }), 200 if redis_ok else 503


@api_bp.route("/info", methods=["GET"])
def system_info():
    """System info and available endpoints."""
    return jsonify({
        "name": "Multi-Agent Orchestration System",
        "version": "2.0.0",
        "agents": ["planner", "retriever", "analyzer", "writer", "critic"],
        "endpoints": {
            "POST /api/v1/token": "Get JWT token",
            "POST /api/v1/workflow": "Start a new workflow",
            "GET  /api/v1/workflow/<id>/status": "Poll workflow status",
            "GET  /api/v1/workflow/<id>/stream": "SSE live updates",
            "GET  /api/v1/workflow/<id>/messages": "Agent message history",
            "GET  /api/v1/sessions": "List all sessions",
            "GET  /api/v1/health": "Health check",
        },
    })
