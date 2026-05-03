"""TTS provider interface — bring your own audio, or plug in a provider."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class TTSProvider(ABC):
    """Synthesize text → audio file. Implementations write to disk and return the path."""

    @abstractmethod
    def synthesize(self, text: str, out_path: str | Path) -> Path:
        """Write spoken `text` to `out_path` and return the actual path written.

        Implementations may rewrite the output extension if their format differs
        from what was passed in (e.g. ElevenLabs returns mp3; the path may be
        rewritten to `.mp3` regardless of caller intent).
        """
        ...


from .byo import BYOProvider  # noqa: E402
from .elevenlabs import ElevenLabsProvider  # noqa: E402
from .moss import MossProvider  # noqa: E402

__all__ = ["TTSProvider", "BYOProvider", "ElevenLabsProvider", "MossProvider"]
