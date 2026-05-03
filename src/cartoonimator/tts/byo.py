"""Bring-your-own-audio provider — pass through a pre-existing WAV/MP3 path."""
from __future__ import annotations

from pathlib import Path

from . import TTSProvider


class BYOProvider(TTSProvider):
    """No synthesis — caller already has audio. The `text` argument is ignored.

    Useful when you've recorded yourself, used another TTS tool, or precomputed
    audio. Pass the existing audio path on construction; `synthesize` returns it.
    """

    def __init__(self, audio_path: str | Path) -> None:
        self.audio_path = Path(audio_path)
        if not self.audio_path.exists():
            raise FileNotFoundError(f"BYOProvider: audio not found at {self.audio_path}")

    def synthesize(self, text: str, out_path: str | Path) -> Path:  # noqa: ARG002
        return self.audio_path
