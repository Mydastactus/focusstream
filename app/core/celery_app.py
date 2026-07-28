from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "focusstream",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks", "app.workers.ingestion"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    timezone="UTC",
)

# Celery beat: poll every active source on a cadence. The task fans out one
# poll_source per source; new items flow into embed -> match -> synthesize.
celery_app.conf.beat_schedule = {
    "poll-all-sources": {
        "task": "ingestion.poll_all_sources",
        "schedule": settings.poll_interval_seconds,
    },
}
