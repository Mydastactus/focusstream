"""Pure unit tests — no DB, no network."""

from app.core.config import settings
from app.models.signal_card import SignalTier
from app.services.scoring import estimate_read_time, tier_for_score


def test_tier_high_signal_at_and_above_threshold():
    assert tier_for_score(0.95) is SignalTier.high_signal
    assert tier_for_score(settings.high_signal_threshold) is SignalTier.high_signal


def test_tier_contextual_band():
    assert tier_for_score(0.80) is SignalTier.contextual
    assert tier_for_score(settings.contextual_threshold) is SignalTier.contextual


def test_tier_low_below_contextual():
    assert tier_for_score(0.50) is SignalTier.low_signal
    # Just under the contextual floor is still low.
    assert tier_for_score(settings.contextual_threshold - 0.001) is SignalTier.low_signal


def test_read_time_empty_is_one_minute():
    assert estimate_read_time(None) == "1 min read"
    assert estimate_read_time("") == "1 min read"


def test_read_time_scales_with_word_count():
    # ~200 wpm -> 400 words ≈ 2 minutes.
    assert estimate_read_time("word " * 400) == "2 min read"
    assert estimate_read_time("word " * 100) == "1 min read"
