"""Whisper transcription with the audio decoder and OpenAI client fully stubbed —
no ffmpeg, no network, no API key needed. Exercises chunking, the duration cap,
the disable switch, and graceful-degradation-to-None on failure."""

import app.services.transcription as trans

_MIN = 60 * 1000  # one minute in ms


class FakeAudio:
    """Minimal stand-in for a pydub AudioSegment."""

    def __init__(self, ms: int):
        self._ms = ms

    def __len__(self) -> int:
        return self._ms

    def __getitem__(self, sl: slice) -> "FakeAudio":
        start = sl.start or 0
        stop = self._ms if sl.stop is None else min(sl.stop, self._ms)
        return FakeAudio(max(0, stop - start))

    def set_channels(self, _n: int) -> "FakeAudio":
        return self

    def set_frame_rate(self, _r: int) -> "FakeAudio":
        return self

    def export(self, path: str, format: str, bitrate: str) -> str:  # noqa: A002
        with open(path, "wb") as fh:
            fh.write(b"x")
        return path


class _FakeTranscriptions:
    def create(self, model, file, response_format):
        return "chunk text"


class FakeClient:
    class audio:  # noqa: N801
        transcriptions = _FakeTranscriptions()


def _patch_common(monkeypatch, audio: FakeAudio):
    monkeypatch.setattr(trans, "_download", lambda url, dest: None)
    monkeypatch.setattr(trans, "AudioSegment", type("Seg", (), {"from_file": staticmethod(lambda p: audio)}))
    monkeypatch.setattr(trans, "_get_client", lambda: FakeClient())
    monkeypatch.setattr(trans.settings, "transcription_enabled", True)


def test_chunks_a_25_minute_episode_into_three(monkeypatch):
    _patch_common(monkeypatch, FakeAudio(25 * _MIN))
    result = trans.transcribe_audio("https://x/ep.mp3")
    # 10-min chunks -> starts at 0, 10, 20 -> 3 transcribed chunks.
    assert result is not None
    assert result.count("chunk text") == 3


def test_duration_cap_limits_chunk_count(monkeypatch):
    monkeypatch.setattr(trans.settings, "podcast_max_duration_minutes", 120)
    _patch_common(monkeypatch, FakeAudio(200 * _MIN))  # 200 min, capped to 120
    result = trans.transcribe_audio("https://x/long.mp3")
    # 120 min / 10-min chunks = 12 chunks (not 20).
    assert result.count("chunk text") == 12


def test_disabled_returns_none(monkeypatch):
    _patch_common(monkeypatch, FakeAudio(10 * _MIN))
    monkeypatch.setattr(trans.settings, "transcription_enabled", False)
    assert trans.transcribe_audio("https://x/ep.mp3") is None


def test_failure_degrades_to_none(monkeypatch):
    monkeypatch.setattr(trans.settings, "transcription_enabled", True)

    def boom(url, dest):
        raise RuntimeError("network down")

    monkeypatch.setattr(trans, "_download", boom)
    assert trans.transcribe_audio("https://x/ep.mp3") is None
