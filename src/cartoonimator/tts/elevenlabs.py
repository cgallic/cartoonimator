"""ElevenLabs TTS provider."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import requests

from . import TTSProvider


class TTSError(RuntimeError):
    pass


@dataclass
class ElevenLabsProvider(TTSProvider):
    """Call ElevenLabs API → write mp3 to disk.

    ElevenLabs free / Starter tiers only allow `mp3_44100_128`; PCM ≥ 22050
    requires Pro+. Output is always mp3 — the caller's `out_path` extension is
    rewritten to `.mp3`. ffmpeg handles audio mux downstream natively.
    """

    voice_id: str
    api_key: str | None = None
    model_id: str = "eleven_multilingual_v2"
    stability: float = 0.5
    similarity_boost: float = 0.75
    style: float = 0.0
    use_speaker_boost: bool = True

    def synthesize(self, text: str, out_path: str | Path) -> Path:
        out_path = Path(out_path)
        if out_path.suffix.lower() != ".mp3":
            out_path = out_path.with_suffix(".mp3")

        key = self.api_key or os.environ.get("ELEVENLABS_API_KEY")
        if not key:
            raise TTSError(
                "ElevenLabsProvider requires an api_key argument or ELEVENLABS_API_KEY env var"
            )

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}"
        headers = {
            "xi-api-key": key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        body = {
            "text": text,
            "model_id": self.model_id,
            "voice_settings": {
                "stability": self.stability,
                "similarity_boost": self.similarity_boost,
                "style": self.style,
                "use_speaker_boost": self.use_speaker_boost,
            },
        }
        params = {"output_format": "mp3_44100_128"}
        resp = requests.post(url, headers=headers, json=body, params=params, timeout=120)
        if resp.status_code != 200:
            raise TTSError(
                f"ElevenLabs HTTP {resp.status_code}: {resp.text[:300]}"
            )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(resp.content)
        return out_path
