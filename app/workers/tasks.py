"""Async pipeline: embed -> match -> synthesize -> persist Signal Cards.

The FastAPI request path only ever dispatches into these tasks; it never blocks
on the embedding model or the LLM.
"""

import secrets
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.database import SyncSessionLocal
from app.models.raw_feed_item import RawFeedItem
from app.models.signal_card import SignalCard
from app.models.sprint import EmbeddingStatus, Sprint, SprintStatus
from app.services.embeddings import embed_text
from app.services.llm import synthesize_takeaway
from app.services.scoring import estimate_read_time, tier_for_score


def _card_id() -> str:
    return f"card_{secrets.token_hex(4)}"


def _set_embedding_status(sprint_id: str, status: EmbeddingStatus) -> None:
    with SyncSessionLocal() as db:
        sprint = db.get(Sprint, sprint_id)
        if sprint is not None:
            sprint.embedding_status = status
            db.commit()


@celery_app.task(name="sprints.embed_intent", bind=True, max_retries=3, default_retry_delay=10)
def embed_sprint_intent(self, sprint_id: str) -> None:
    """Compute and persist the intent embedding for a newly created sprint.

    On the final failed attempt, mark the sprint `failed` so the UI can offer a
    retry instead of showing "Indexing…" forever.
    """
    try:
        with SyncSessionLocal() as db:
            sprint = db.get(Sprint, sprint_id)
            if sprint is None:
                return
            sprint.intent_embedding = embed_text(f"{sprint.title}\n\n{sprint.description}")
            sprint.embedding_status = EmbeddingStatus.ready
            db.commit()
    except Exception as exc:  # noqa: BLE001
        if self.request.retries >= self.max_retries:
            _set_embedding_status(sprint_id, EmbeddingStatus.failed)
            raise
        raise self.retry(exc=exc)


@celery_app.task(name="content.embed_item", bind=True, max_retries=3, default_retry_delay=10)
def embed_content_item(self, raw_item_id: str) -> None:
    """Embed a raw feed item, then hand off to the matching engine."""
    try:
        with SyncSessionLocal() as db:
            item = db.get(RawFeedItem, raw_item_id)
            if item is None:
                return
            if item.embedding is None:
                item.embedding = embed_text(f"{item.title}\n\n{item.body or ''}")
                db.commit()
        match_item_to_sprints.delay(raw_item_id)
    except Exception as exc:  # noqa: BLE001
        raise self.retry(exc=exc)


@celery_app.task(name="content.match_item")
def match_item_to_sprints(raw_item_id: str) -> None:
    """Score a freshly embedded item against every active sprint via pgvector
    cosine similarity, synthesize a takeaway for high-signal matches, and persist
    a Signal Card per surfaced match."""
    with SyncSessionLocal() as db:
        item = db.get(RawFeedItem, raw_item_id)
        if item is None or item.embedding is None:
            return

        # Match against active sprints that already have an intent vector and
        # whose sources_allowed permits this item's source type.
        stmt = (
            select(
                Sprint,
                Sprint.intent_embedding.cosine_distance(item.embedding).label("distance"),
            )
            .where(Sprint.status == SprintStatus.active)
            .where(Sprint.intent_embedding.isnot(None))
            .where(Sprint.sources_allowed.any(item.source_type.value))
        )

        read_time = estimate_read_time(item.body)

        for sprint, distance in db.execute(stmt).all():
            # pgvector cosine_distance = 1 - cosine_similarity.
            score = 1.0 - float(distance)
            tier = tier_for_score(score)

            # Archive (skip) anything below the contextual floor.
            if score < settings.min_store_threshold:
                continue

            # Idempotency: one card per (sprint, item).
            already = db.execute(
                select(SignalCard.id).where(
                    SignalCard.intent_sprint_id == sprint.id,
                    SignalCard.raw_item_id == item.id,
                )
            ).first()
            if already is not None:
                continue

            ai_summary = None
            if tier.value in settings.synthesize_tiers:
                ai_summary = synthesize_takeaway(
                    sprint.title, sprint.description, item.title, item.body or ""
                )

            db.add(
                SignalCard(
                    id=_card_id(),
                    intent_sprint_id=sprint.id,
                    raw_item_id=item.id,
                    signal_score=round(score, 4),
                    signal_tier=tier,
                    ai_summary=ai_summary,
                    estimated_read_time=read_time,
                )
            )

        item.processed_at = datetime.now(timezone.utc)
        db.commit()
