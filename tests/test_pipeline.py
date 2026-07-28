"""Worker-pipeline integration tests (require Postgres+pgvector).

The embedder (OpenAI) and synthesizer (Claude) are stubbed; the pgvector cosine
match itself runs for real against the test DB.
"""

from sqlalchemy import select

from app.models import RawFeedItem, SignalCard, SourceType, Sprint, SprintStatus, User
from app.models.sprint import EmbeddingStatus
from tests.conftest import vec


def _seed_user(db, uid="usr_1"):
    db.add(User(id=uid, email=f"{uid}@focusstream.app"))


async def test_embed_content_item_sets_vector_and_dispatches_match(sync_db, monkeypatch):
    from app.core.config import settings
    from app.workers import tasks

    fixed = vec(settings.embedding_dim)
    monkeypatch.setattr(tasks, "embed_text", lambda text: fixed)  # stub embedder

    sync_db.add(
        RawFeedItem(
            id="item_1",
            source_type=SourceType.rss,
            source_name="TechCrunch",
            title="EU AI Act",
            body="Enforcement begins in August.",
            content_hash="h1",
        )
    )
    sync_db.commit()

    tasks.embed_content_item.apply(args=["item_1"])

    sync_db.expire_all()
    item = sync_db.get(RawFeedItem, "item_1")
    assert item.embedding is not None
    # Matching is handed off to the next stage.
    tasks.match_item_to_sprints.delay.assert_called_once_with("item_1")


async def test_match_creates_high_signal_card_with_synthesized_summary(sync_db, monkeypatch):
    from app.core.config import settings
    from app.workers import tasks

    monkeypatch.setattr(
        tasks, "synthesize_takeaway", lambda *a, **k: "Audit trails are now mandatory."
    )

    dim = settings.embedding_dim
    _seed_user(sync_db)
    # Sprint and item share an identical vector -> cosine distance 0 -> score 1.0.
    sync_db.add(
        Sprint(
            id="spr_1",
            user_id="usr_1",
            title="AI Compliance Audit",
            description="EU AI Act enforcement.",
            duration_days=14,
            sources_allowed=["rss"],
            status=SprintStatus.active,
            embedding_status=EmbeddingStatus.ready,
            intent_embedding=vec(dim),
        )
    )
    sync_db.add(
        RawFeedItem(
            id="item_1",
            source_type=SourceType.rss,
            source_name="TechCrunch",
            title="EU AI Act Enforcement Dates Confirmed",
            body="Mandatory audit trails for LLM deployments.",
            content_hash="h1",
            embedding=vec(dim),
        )
    )
    sync_db.commit()

    tasks.match_item_to_sprints.apply(args=["item_1"])

    sync_db.expire_all()
    card = sync_db.execute(
        select(SignalCard).where(SignalCard.raw_item_id == "item_1")
    ).scalar_one()
    assert card.intent_sprint_id == "spr_1"
    assert card.signal_tier.value == "high_signal"
    assert card.signal_score >= 0.99  # identical vectors
    assert card.ai_summary == "Audit trails are now mandatory."
    assert card.estimated_read_time is not None


async def test_match_skips_sprint_when_source_not_allowed(sync_db, monkeypatch):
    from app.core.config import settings
    from app.workers import tasks

    called = {"n": 0}

    def _synth(*a, **k):
        called["n"] += 1
        return "x"

    monkeypatch.setattr(tasks, "synthesize_takeaway", _synth)

    dim = settings.embedding_dim
    _seed_user(sync_db)
    # Sprint allows only podcasts; the item is rss -> no match, no synthesis.
    sync_db.add(
        Sprint(
            id="spr_1",
            user_id="usr_1",
            title="Podcast-only sprint",
            description="d",
            duration_days=14,
            sources_allowed=["podcasts"],
            status=SprintStatus.active,
            embedding_status=EmbeddingStatus.ready,
            intent_embedding=vec(dim),
        )
    )
    sync_db.add(
        RawFeedItem(
            id="item_1",
            source_type=SourceType.rss,
            source_name="TechCrunch",
            title="An RSS article",
            body="body",
            content_hash="h1",
            embedding=vec(dim),
        )
    )
    sync_db.commit()

    tasks.match_item_to_sprints.apply(args=["item_1"])

    sync_db.expire_all()
    cards = sync_db.execute(select(SignalCard)).scalars().all()
    assert cards == []
    assert called["n"] == 0
