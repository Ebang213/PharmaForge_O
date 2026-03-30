"""
Celery application configuration.

Uses Redis as the message broker and result backend.
Workers are started via:
    celery -A app.core.celery_app worker --loglevel=info
"""
from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "pharmaforge",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.tasks.watchtower_tasks",
        "app.tasks.evidence_tasks",
        "app.tasks.workflow_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=86400,  # Results expire after 24 hours
)

# Alias so `celery -A app.core.celery_app worker` discovers the app automatically.
app = celery_app
