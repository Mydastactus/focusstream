"""Feed fetching + parsing. Network-facing; only Celery workers call this, never
the request path. Handles RSS, newsletter (Substack-style RSS), and podcast
feeds uniformly — for podcasts we currently index the episode title + show
notes; audio transcription (Whisper) is a future enhancement noted below.
"""

import hashlib
import re
from dataclasses import dataclass

import feedparser

_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class ParsedEntry:
    guid: str
    title: str
    body: str
    url: str | None
    thumbnail: str | None
    audio_url: str | None


def content_hash(source_id: str, guid: str) -> str:
    """Stable de-dup key. Scoped by source so the same URL syndicated by two
    sources still produces two items."""
    return hashlib.sha256(f"{source_id}:{guid}".encode()).hexdigest()


def _strip_html(text: str) -> str:
    return _TAG_RE.sub("", text or "").strip()


def _extract_body(entry) -> str:
    if getattr(entry, "content", None):
        raw = entry.content[0].get("value", "")
    else:
        raw = getattr(entry, "summary", "") or getattr(entry, "description", "")
    return _strip_html(raw)


def _extract_thumbnail(entry) -> str | None:
    media = getattr(entry, "media_thumbnail", None) or getattr(entry, "media_content", None)
    if media:
        url = media[0].get("url")
        if url:
            return url
    for enc in getattr(entry, "enclosures", []) or []:
        if str(enc.get("type", "")).startswith("image"):
            return enc.get("href") or enc.get("url")
    return None


def _extract_audio(entry) -> str | None:
    """Podcast audio enclosure, if present."""
    for enc in getattr(entry, "enclosures", []) or []:
        if str(enc.get("type", "")).startswith("audio"):
            return enc.get("href") or enc.get("url")
    for link in getattr(entry, "links", []) or []:
        if link.get("rel") == "enclosure" and str(link.get("type", "")).startswith("audio"):
            return link.get("href")
    return None


def fetch_feed_entries(feed_url: str, limit: int = 50) -> list[ParsedEntry]:
    parsed = feedparser.parse(feed_url)
    entries: list[ParsedEntry] = []
    for e in parsed.entries[:limit]:
        title = (getattr(e, "title", "") or "").strip()
        if not title:
            continue
        guid = getattr(e, "id", None) or getattr(e, "link", None) or title
        entries.append(
            ParsedEntry(
                guid=str(guid),
                title=title,
                body=_extract_body(e),
                url=getattr(e, "link", None),
                thumbnail=_extract_thumbnail(e),
                audio_url=_extract_audio(e),
            )
        )
    return entries
