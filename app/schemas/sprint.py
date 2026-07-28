from typing import Literal

from pydantic import BaseModel, Field, field_validator

AllowedSource = Literal["rss", "newsletters", "podcasts"]


# The create-sprint modal collects only title + description. duration_days and
# sources_allowed have no UI yet, so they default here; description may be blank.
DEFAULT_SOURCES: list[str] = ["newsletters", "podcasts", "rss"]


class CreateSprintRequest(BaseModel):
    user_id: str = Field(..., examples=["usr_9921"])
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field("", max_length=2000)
    duration_days: int = Field(14, gt=0, le=365)
    sources_allowed: list[AllowedSource] = Field(
        default_factory=lambda: list(DEFAULT_SOURCES), min_length=1
    )

    @field_validator("sources_allowed")
    @classmethod
    def dedupe_sources(cls, v: list[str]) -> list[str]:
        return sorted(set(v))


class CreateSprintResponse(BaseModel):
    sprint_id: str
    status: str
    embedding_status: str  # "queued" — the intent vector is computed async


class SprintSummary(BaseModel):
    """Shape consumed by the frontend sprint list. `status` is derived, not the
    raw DB enum: an active sprint whose intent vector hasn't landed yet reports
    `indexing`; if embedding exhausted its retries it reports `failed` (offer a
    retry) instead of hanging on `indexing` forever."""

    id: str
    title: str
    status: Literal["active", "indexing", "completed", "failed"]
    item_count: int


class RetryEmbeddingResponse(BaseModel):
    sprint_id: str
    embedding_status: str
