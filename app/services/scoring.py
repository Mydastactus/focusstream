"""Pure scoring helpers. Tier thresholds live here (in config), not in the DB,
so they can be tuned against real score distributions without a migration."""

from app.core.config import settings
from app.models.signal_card import SignalTier


def tier_for_score(score: float) -> SignalTier:
    if score >= settings.high_signal_threshold:
        return SignalTier.high_signal
    if score >= settings.contextual_threshold:
        return SignalTier.contextual
    return SignalTier.low_signal


def estimate_read_time(text: str | None) -> str:
    words = len((text or "").split())
    minutes = max(1, round(words / 200))  # ~200 wpm
    return f"{minutes} min read"
