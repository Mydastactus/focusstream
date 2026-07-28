"""Seed a demo user and a few public content sources so the pipeline has
something to ingest. Idempotent — safe to run repeatedly.

    docker compose exec api python -m app.scripts.seed
"""

import secrets

from sqlalchemy import select

from app.core.database import SyncSessionLocal
from app.models.raw_feed_item import SourceType
from app.models.source import Source
from app.models.user import User

DEMO_USER_ID = "usr_9921"  # matches HARDCODED_USER_ID in the mobile app

def _favicon(domain: str) -> str:
    # Populates source.avatar_url with a real image so the frontend (which types
    # it non-null) always has something to render.
    return f"https://www.google.com/s2/favicons?domain={domain}&sz=64"


# (name, type, url, avatar_url, is_active). The podcast is seeded INACTIVE so it
# doesn't incur Whisper transcription cost until you flip it on:
#   UPDATE sources SET is_active = true WHERE type = 'podcasts';
SOURCES: list[tuple[str, SourceType, str, str, bool]] = [
    ("TechCrunch", SourceType.rss, "https://techcrunch.com/feed/", _favicon("techcrunch.com"), True),
    ("The Verge", SourceType.rss, "https://www.theverge.com/rss/index.xml", _favicon("theverge.com"), True),
    ("Ars Technica", SourceType.rss, "https://feeds.arstechnica.com/arstechnica/index", _favicon("arstechnica.com"), True),
    ("Hacker News Front Page", SourceType.rss, "https://hnrss.org/frontpage", _favicon("ycombinator.com"), True),
    ("Talk Python To Me", SourceType.podcasts, "https://talkpython.fm/episodes/rss", _favicon("talkpython.fm"), False),
]


def _source_id() -> str:
    return f"src_{secrets.token_hex(4)}"


def main() -> None:
    with SyncSessionLocal() as db:
        if db.get(User, DEMO_USER_ID) is None:
            db.add(
                User(id=DEMO_USER_ID, email="demo@focusstream.app", display_name="Demo")
            )

        for name, stype, url, avatar_url, is_active in SOURCES:
            if db.execute(select(Source.id).where(Source.url == url)).first() is None:
                db.add(
                    Source(
                        id=_source_id(),
                        name=name,
                        type=stype,
                        url=url,
                        avatar_url=avatar_url,
                        is_active=is_active,
                    )
                )

        db.commit()
    print("Seed complete: demo user + sources ensured (podcast source inactive).")


if __name__ == "__main__":
    main()
