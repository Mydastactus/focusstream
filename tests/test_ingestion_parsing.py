"""Feed parsing tests. feedparser.parse() accepts a raw XML string, so these run
fully offline — no network."""

from app.services.ingestion import content_hash, fetch_feed_entries

RSS = """<?xml version="1.0"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
  <channel>
    <title>Test Feed</title>
    <item>
      <title>EU AI Act Enforcement Dates Confirmed</title>
      <link>https://example.com/article</link>
      <guid>https://example.com/article</guid>
      <description>Enforcement begins in &lt;b&gt;August 2026&lt;/b&gt;.</description>
      <media:thumbnail url="https://example.com/thumb.jpg"/>
    </item>
    <item>
      <title></title>
      <link>https://example.com/no-title</link>
    </item>
  </channel>
</rss>
"""

PODCAST_RSS = """<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>Test Podcast</title>
    <item>
      <title>Episode 1: Compliance Deep Dive</title>
      <link>https://example.com/ep1</link>
      <guid>ep1</guid>
      <description>Show notes about audits.</description>
      <enclosure url="https://example.com/ep1.mp3" type="audio/mpeg" length="12345"/>
    </item>
  </channel>
</rss>
"""


def test_content_hash_is_stable_and_source_scoped():
    a = content_hash("src_1", "guid-x")
    assert a == content_hash("src_1", "guid-x")  # deterministic
    assert a != content_hash("src_2", "guid-x")  # scoped by source


def test_rss_entry_extraction_and_html_stripping():
    entries = fetch_feed_entries(RSS)
    # The empty-title item is skipped.
    assert len(entries) == 1
    e = entries[0]
    assert e.title == "EU AI Act Enforcement Dates Confirmed"
    assert e.body == "Enforcement begins in August 2026."  # tags stripped
    assert e.url == "https://example.com/article"
    assert e.thumbnail == "https://example.com/thumb.jpg"
    assert e.audio_url is None


def test_podcast_audio_enclosure_extracted():
    entries = fetch_feed_entries(PODCAST_RSS)
    assert len(entries) == 1
    assert entries[0].audio_url == "https://example.com/ep1.mp3"
