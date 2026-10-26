"""
Prometheus metrics for the multi-agent orchestration system.
Exposes /metrics endpoint for Grafana/Prometheus scraping.
"""
from __future__ import annotations
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from flask import Response

# ── Counters ──────────────────────────────────────────────────────────────────
WORKFLOW_STARTED = Counter(
    "multiagent_workflows_started_total",
    "Total number of workflows started",
    ["priority"],
)

WORKFLOW_COMPLETED = Counter(
    "multiagent_workflows_completed_total",
    "Total number of completed workflows",
    ["status"],  # completed | failed
)

AGENT_CALLS = Counter(
    "multiagent_agent_calls_total",
    "Total LLM calls per agent",
    ["agent_role"],
)

TOOL_CALLS = Counter(
    "multiagent_tool_calls_total",
    "Total tool invocations",
    ["tool_name", "success"],
)

CRITIC_REVISIONS = Counter(
    "multiagent_critic_revisions_total",
    "Total revision cycles requested by critic",
)

# ── Histograms ────────────────────────────────────────────────────────────────
WORKFLOW_DURATION = Histogram(
    "multiagent_workflow_duration_seconds",
    "Workflow end-to-end duration",
    buckets=[5, 10, 30, 60, 120, 300, 600],
)

AGENT_LATENCY = Histogram(
    "multiagent_agent_latency_seconds",
    "Per-agent execution latency",
    ["agent_role"],
    buckets=[1, 2, 5, 10, 30, 60],
)

# ── Gauges ────────────────────────────────────────────────────────────────────
ACTIVE_SESSIONS = Gauge(
    "multiagent_active_sessions",
    "Number of currently active sessions",
)

QUEUE_DEPTH = Gauge(
    "multiagent_queue_depth",
    "Tasks waiting in Celery queue",
    ["queue_name"],
)


def metrics_endpoint() -> Response:
    """Flask handler that returns Prometheus metrics."""
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)
