"""Trigger an ingestion poll immediately instead of waiting for Celery beat.

    docker compose exec worker python -m app.scripts.poll_now
"""

from app.workers.ingestion import poll_all_sources


def main() -> None:
    poll_all_sources.delay()
    print("Enqueued ingestion.poll_all_sources")


if __name__ == "__main__":
    main()
