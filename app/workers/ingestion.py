"""Ingestion tasks: poll sources -> persist new items (deduped) -> hand each new
item to the embedding pipeline (`embed_content_item`), which then matches and
synthesizes. Scheduled by Celery beat; see app/core/celery_app.py.
"""

import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.database import SyncSessionLocal
from app.models.raw_feed_item import RawFeedItem, SourceType
from app.models.source import Source
from app.services.ingestion import content_hash, fetch_feed_entries
from app.services.transcription import transcribe_audio
from app.workers.tasks import embed_content_item


def _item_id() -> str:
    return f"item_{secrets.token_hex(4)}"


@celery_app.task(name="ingestion.poll_all_sources")
def poll_all_sources() -> None:
    """Fan out one poll task per active source."""
    with SyncSessionLocal() as db:
        source_ids = (
            db.execute(select(Source.id).where(Source.is_active.is_(True)))
            .scalars()
            .all()
        )
    for source_id in source_ids:
        poll_source.delay(source_id)


@celery_app.task(
    name="ingestion.poll_source", bind=True, max_retries=3, default_retry_delay=30
)
def poll_source(self, source_id: str) -> None:
    """Fetch one source, persist new items (deduped by content_hash), and hand
    each new item to the embedding pipeline."""
    try:
        new_item_ids: list[str] = []
        with SyncSessionLocal() as db:
            source = db.get(Source, source_id)
            if source is None or not source.is_active:
                return
            src_type = source.type

            for entry in fetch_feed_entries(source.url):
                digest = content_hash(source.id, entry.guid)
                if db.execute(
                    select(RawFeedItem.id).where(RawFeedItem.content_hash == digest)
                ).first():
                    continue

                item = RawFeedItem(
                    id=_item_id(),
                    source_type=source.type,
                    source_name=source.name,
                    source_avatar_url=source.avatar_url,
                    title=entry.title,
                    body=entry.body,
                    url=entry.url,
                    thumbnail_url=entry.thumbnail,
                    audio_url=entry.audio_url,
                    content_hash=digest,
                )
                # SAVEPOINT per item: a duplicate racing a concurrent poll of the
                # same source rolls back only this item, not the whole batch.
                try:
                    with db.begin_nested():
                        db.add(item)
                        db.flush()
                except IntegrityError:
                    continue
                new_item_ids.append(item.id)

            source.last_polled_at = datetime.now(timezone.utc)
            db.commit()

        # Dispatch after commit so the rows are visible to the workers.
        # Podcasts route through transcription first; the newest N episodes are
        # transcribed (cost throttle), older backlog embeds on show notes only.
        # new_item_ids is in feed order (newest first).
        if src_type == SourceType.podcasts:
            cap = settings.podcast_max_episodes_per_poll
            for item_id in new_item_ids[:cap]:
                transcribe_podcast.delay(item_id)
            for item_id in new_item_ids[cap:]:
                embed_content_item.delay(item_id)
        else:
            for item_id in new_item_ids:
                embed_content_item.delay(item_id)
    except Exception as exc:  # noqa: BLE001
        raise self.retry(exc=exc)


@celery_app.task(
    name="content.transcribe_podcast", bind=True, max_retries=2, default_retry_delay=60
)
def transcribe_podcast(self, raw_item_id: str) -> None:
    """Transcribe a podcast episode's audio, fold the transcript into the item
    body, then hand off to the embedding pipeline. Degrades to show-notes-only
    matching if transcription fails."""
    # Read the audio URL, then release the DB session — transcription is a
    # minutes-long network+CPU job and must not hold a transaction open.
    with SyncSessionLocal() as db:
        item = db.get(RawFeedItem, raw_item_id)
        if item is None:
            return
        audio_url = item.audio_url
        show_notes = item.body or ""

    transcript = transcribe_audio(audio_url) if audio_url else None

    if transcript:
        with SyncSessionLocal() as db:
            item = db.get(RawFeedItem, raw_item_id)
            if item is None:
                return
            # Transcript is the gold signal; keep show notes as leading context.
            item.body = f"{show_notes}\n\n{transcript}".strip() if show_notes else transcript
            db.commit()

    embed_content_item.delay(raw_item_id)
