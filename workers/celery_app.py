"""
Celery application configuration with priority queues and task routing.
"""
from __future__ import annotations
import os
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

celery_app = Celery(
    "multiagent",
    broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"),
    include=["workers.tasks"],
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # Timezone
    timezone="UTC",
    enable_utc=True,
    # Result expiration (1 hour)
    result_expires=3600,
    # Priority queues
    task_queues={
        "high": {"exchange": "high", "routing_key": "high"},
        "medium": {"exchange": "medium", "routing_key": "medium"},
        "low": {"exchange": "low", "routing_key": "low"},
    },
    task_default_queue="medium",
    task_default_exchange="medium",
    task_default_routing_key="medium",
    # Retry settings
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    # Track task starts for accurate status
    task_track_started=True,
    # Dead letter queue — tasks that fail all retries go here
    task_routes={
        "workers.tasks.run_workflow_task": {"queue": "medium"},
    },
)
