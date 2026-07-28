"""Whisper transcription for podcast audio.

Podcast episodes routinely exceed the Whisper API's 25 MB / single-file limit,
so we downsample to 16 kHz mono and split into fixed-length chunks, transcribe
each, and concatenate. Failures degrade gracefully (return None) — the caller
then embeds on show notes alone rather than dropping the item.
"""

import os
import shutil
import tempfile
from urllib.parse import urlparse

import httpx
from openai import OpenAI
from pydub import AudioSegment

from app.core.config import settings

_client: OpenAI | None = None

# 10-minute chunks at 64 kbps mp3 ≈ 4.8 MB — comfortably under the 25 MB limit.
_CHUNK_MS = 10 * 60 * 1000
_CHUNK_BITRATE = "64k"


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


def _download(url: str, dest: str) -> None:
    with httpx.stream("GET", url, follow_redirects=True, timeout=120.0) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in resp.iter_bytes():
                fh.write(chunk)


def transcribe_audio(url: str) -> str | None:
    """Transcribe a podcast episode. Returns the transcript, or None on any
    failure / when transcription is disabled."""
    if not settings.transcription_enabled:
        return None

    tmpdir = tempfile.mkdtemp(prefix="fs_transcribe_")
    try:
        ext = os.path.splitext(urlparse(url).path)[1] or ".mp3"
        audio_path = os.path.join(tmpdir, f"audio{ext}")
        _download(url, audio_path)

        audio = AudioSegment.from_file(audio_path)

        # Cap duration (cost) and downsample (size) before chunking.
        max_ms = settings.podcast_max_duration_minutes * 60 * 1000
        if len(audio) > max_ms:
            audio = audio[:max_ms]
        audio = audio.set_channels(1).set_frame_rate(16000)

        transcripts: list[str] = []
        for start in range(0, len(audio), _CHUNK_MS):
            chunk_path = os.path.join(tmpdir, f"chunk_{start}.mp3")
            audio[start : start + _CHUNK_MS].export(
                chunk_path, format="mp3", bitrate=_CHUNK_BITRATE
            )
            with open(chunk_path, "rb") as fh:
                text = _get_client().audio.transcriptions.create(
                    model=settings.whisper_model,
                    file=fh,
                    response_format="text",
                )
            # response_format="text" yields a plain string.
            transcripts.append(text if isinstance(text, str) else getattr(text, "text", ""))

        joined = "\n".join(t.strip() for t in transcripts if t).strip()
        return joined or None
    except Exception:  # noqa: BLE001  — degrade to metadata-only on any failure
        return None
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
