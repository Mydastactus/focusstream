"""Embedding provider wrapper. Isolated so the provider can be swapped without
touching the pipeline."""

from openai import OpenAI

from app.core.config import settings

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


def embed_text(text: str) -> list[float]:
    """Return an embedding vector for the given text.

    `dimensions` truncates text-embedding-3-large via Matryoshka so the output
    stays at settings.embedding_dim (<= 2000, keeping the pgvector index valid).
    """
    resp = _get_client().embeddings.create(
        model=settings.embedding_model,
        input=text[:8000],  # guard overly long inputs
        dimensions=settings.embedding_dim,
    )
    return resp.data[0].embedding
