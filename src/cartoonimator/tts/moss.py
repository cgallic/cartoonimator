"""MOSS-TTS provider — for users running a self-hosted MOSS-TTS server.

MOSS-TTS is a voice-cloning TTS that runs locally on a GPU. This provider
talks to its HTTP API. Construction requires an explicit host, port, and
voice reference WAV path on the MOSS server — no defaults are baked in.

Example:
    provider = MossProvider(
        host="my-gpu-box",
        port=8091,
        reference_path="/path/on/moss/server/to/voice_reference.wav",
    )
    audio = provider.synthesize("Hello there.", "out.wav")
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import requests

from . import TTSProvider


class TTSError(RuntimeError):
    pass


@dataclass
class MossProvider(TTSProvider):
    """HTTP client for a MOSS-TTS server.

    Args:
        host: hostname or IP where MOSS-TTS is listening
        port: port (default 8091)
        reference_path: absolute path on the MOSS server to a reference WAV
            (the voice MOSS clones for this synthesis call)
        timeout_s: HTTP timeout in seconds
    """

    host: str
    port: int = 8091
    reference_path: str = ""
    timeout_s: float = 180.0

    def synthesize(self, text: str, out_path: str | Path) -> Path:
        if not self.reference_path:
            raise TTSError(
                "MossProvider.reference_path is required — pass the absolute path "
                "of a voice reference WAV on the MOSS server."
            )
        out_path = Path(out_path)
        if out_path.suffix.lower() != ".wav":
            out_path = out_path.with_suffix(".wav")

        url = f"http://{self.host}:{self.port}/tts"
        body = {"text": text, "reference": self.reference_path}
        resp = requests.post(url, json=body, timeout=self.timeout_s)
        if resp.status_code != 200:
            raise TTSError(
                f"MOSS-TTS HTTP {resp.status_code}: {resp.text[:300]}"
            )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(resp.content)
        return out_path
