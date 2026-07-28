"""The derived sprint status the frontend consumes (active/indexing/completed/failed)."""

from app.api.v1.users import _display_status
from app.models.sprint import EmbeddingStatus, SprintStatus


def test_active_sprint_without_vector_is_indexing():
    assert _display_status(SprintStatus.active, EmbeddingStatus.pending) == "indexing"


def test_active_sprint_with_vector_is_active():
    assert _display_status(SprintStatus.active, EmbeddingStatus.ready) == "active"


def test_active_sprint_with_failed_embedding_is_failed():
    assert _display_status(SprintStatus.active, EmbeddingStatus.failed) == "failed"


def test_completed_and_archived_both_map_to_completed():
    assert _display_status(SprintStatus.completed, EmbeddingStatus.ready) == "completed"
    # archived has no frontend state -> surfaced as completed, regardless of vector.
    assert _display_status(SprintStatus.archived, EmbeddingStatus.pending) == "completed"
