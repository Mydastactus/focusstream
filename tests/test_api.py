"""API integration tests (require Postgres+pgvector — skipped otherwise)."""

from app.models import RawFeedItem, SignalCard, SignalTier, SourceType, Sprint, SprintStatus, User


def _user(uid="usr_1"):
    return User(id=uid, email=f"{uid}@focusstream.app")


def _sprint(sid="spr_1", uid="usr_1", status=SprintStatus.active, embedding=None):
    from app.models.sprint import EmbeddingStatus

    return Sprint(
        id=sid,
        user_id=uid,
        title="Prepare for AI Compliance Audit",
        description="EU AI Act enforcement.",
        duration_days=14,
        sources_allowed=["rss"],
        status=status,
        embedding_status=EmbeddingStatus.pending,
        intent_embedding=embedding,
    )


def _item(iid="item_1", chash="h1"):
    return RawFeedItem(
        id=iid,
        source_type=SourceType.rss,
        source_name="TechCrunch",
        title="EU AI Act Enforcement Dates Confirmed",
        body="Enforcement begins in August.",
        content_hash=chash,
    )


def _card(cid, sprint_id, item_id, score):
    return SignalCard(
        id=cid,
        intent_sprint_id=sprint_id,
        raw_item_id=item_id,
        signal_score=score,
        signal_tier=SignalTier.high_signal,
    )


async def test_create_sprint_returns_201_and_dispatches_embedding(client, sync_db):
    from app.workers import tasks

    sync_db.add(_user())
    sync_db.commit()

    resp = await client.post(
        "/api/v1/sprints",
        json={"user_id": "usr_1", "title": "Audit prep", "description": "EU AI Act"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["sprint_id"].startswith("spr_")
    assert body["embedding_status"] == "queued"

    # Embedding was queued exactly once for the new sprint.
    tasks.embed_sprint_intent.delay.assert_called_once_with(body["sprint_id"])


async def test_create_sprint_unknown_user_404(client):
    resp = await client.post(
        "/api/v1/sprints",
        json={"user_id": "ghost", "title": "x", "description": "y"},
    )
    assert resp.status_code == 404


async def test_create_sprint_defaults_when_minimal_payload(client, sync_db):
    from sqlalchemy import select

    sync_db.add(_user())
    sync_db.commit()

    resp = await client.post(
        "/api/v1/sprints",
        json={"user_id": "usr_1", "title": "Only a title"},  # no description/duration/sources
    )
    assert resp.status_code == 201
    sid = resp.json()["sprint_id"]

    sprint = sync_db.execute(select(Sprint).where(Sprint.id == sid)).scalar_one()
    assert sprint.duration_days == 14
    assert set(sprint.sources_allowed) == {"newsletters", "podcasts", "rss"}


async def test_downvote_hides_card_from_feed(client, sync_db):
    sync_db.add_all([_user(), _sprint(), _item(), _card("card_1", "spr_1", "item_1", 0.95)])
    sync_db.commit()

    resp = await client.get("/api/v1/sprints/spr_1/feed")
    assert resp.status_code == 200
    assert resp.json()["total_items"] == 1

    resp = await client.post(
        "/api/v1/feedback", json={"item_id": "card_1", "action": "downvote"}
    )
    assert resp.status_code == 201

    # Downvoted card no longer appears on refresh (the reappear bug).
    resp = await client.get("/api/v1/sprints/spr_1/feed")
    assert resp.json()["total_items"] == 0


async def test_sprint_status_lifecycle(client, sync_db):
    from app.models.sprint import EmbeddingStatus

    sync_db.add_all([_user(), _sprint()])
    sync_db.commit()

    async def status():
        resp = await client.get("/api/v1/users/usr_1/sprints")
        return resp.json()[0]["status"]

    assert await status() == "indexing"  # pending vector

    sprint = sync_db.get(Sprint, "spr_1")
    sprint.embedding_status = EmbeddingStatus.ready
    sync_db.commit()
    assert await status() == "active"

    sprint.embedding_status = EmbeddingStatus.failed
    sync_db.commit()
    assert await status() == "failed"


async def test_retry_embedding_requeues_failed_sprint(client, sync_db):
    from app.models.sprint import EmbeddingStatus
    from app.workers import tasks

    s = _sprint()
    s.embedding_status = EmbeddingStatus.failed
    sync_db.add_all([_user(), s])
    sync_db.commit()

    resp = await client.post("/api/v1/sprints/spr_1/embedding/retry")
    assert resp.status_code == 200
    assert resp.json()["embedding_status"] == "queued"
    tasks.embed_sprint_intent.delay.assert_called_once_with("spr_1")

    sync_db.expire_all()
    assert sync_db.get(Sprint, "spr_1").embedding_status == EmbeddingStatus.pending


async def test_retry_embedding_conflict_when_ready(client, sync_db):
    from app.models.sprint import EmbeddingStatus

    s = _sprint()
    s.embedding_status = EmbeddingStatus.ready
    sync_db.add_all([_user(), s])
    sync_db.commit()

    resp = await client.post("/api/v1/sprints/spr_1/embedding/retry")
    assert resp.status_code == 409


async def test_aggregate_feed_dedupes_and_respects_dismiss(client, sync_db):
    # One item matched to two active sprints -> two cards, different scores.
    sync_db.add_all(
        [
            _user(),
            _sprint("spr_1"),
            _sprint("spr_2"),
            _item("item_1", "h1"),
            _card("card_lo", "spr_1", "item_1", 0.80),
            _card("card_hi", "spr_2", "item_1", 0.95),
        ]
    )
    sync_db.commit()

    resp = await client.get("/api/v1/users/usr_1/feed")
    assert resp.status_code == 200
    body = resp.json()
    # Deduped to one item, keeping the higher-scoring card.
    assert body["total_items"] == 1
    assert body["items"][0]["card_id"] == "card_hi"

    # Dismiss the winner -> the other card surfaces.
    await client.post("/api/v1/feedback", json={"item_id": "card_hi", "action": "downvote"})
    resp = await client.get("/api/v1/users/usr_1/feed")
    body = resp.json()
    assert body["total_items"] == 1
    assert body["items"][0]["card_id"] == "card_lo"
