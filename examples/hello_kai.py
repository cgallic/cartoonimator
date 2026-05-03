"""Render Kai saying a single sentence.

Prereqs:
    pip install -e .
    apt-get install ffmpeg                                  # or brew install ffmpeg
    # Rhubarb: https://github.com/DanielSWolf/rhubarb-lip-sync/releases
    # Mascot PNGs: clone the repo (Kai's poses are in mascots/kai/poses/)

Usage:
    # supply your own .wav (record yourself, or use any TTS):
    python examples/hello_kai.py path/to/voice.wav out.mp4

    # or — if you have an ElevenLabs API key:
    ELEVENLABS_API_KEY=... python examples/hello_kai.py --eleven out.mp4
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from cartoonimator import load_mascot, render_scene

REPO_ROOT = Path(__file__).resolve().parents[1]
KAI_DIR = REPO_ROOT / "mascots" / "kai"
BG_PATH = REPO_ROOT / "assets" / "backgrounds" / "solid_deep_navy_1080x1920.png"
SCRIPT = (
    "Hi, I'm Kai. AI illustrates, code animates. The body never moves between "
    "frames, so there's no wobble. The mouth follows the audio. That's it."
)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("audio", nargs="?", help="path to a WAV file (or .mp3)")
    p.add_argument("output", help="path to output MP4")
    p.add_argument("--eleven", action="store_true",
                   help="generate audio with ElevenLabs (needs ELEVENLABS_API_KEY)")
    p.add_argument("--voice-id", default="21m00Tcm4TlvDq8ikWAM",
                   help="ElevenLabs voice ID (default: Rachel)")
    args = p.parse_args()

    if args.eleven:
        from cartoonimator.tts import ElevenLabsProvider
        provider = ElevenLabsProvider(voice_id=args.voice_id)
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            audio_path = provider.synthesize(SCRIPT, tmp.name)
    elif args.audio:
        audio_path = Path(args.audio)
    else:
        sys.stderr.write("error: provide an audio path, or pass --eleven\n")
        return 2

    out = render_scene(
        mascot=load_mascot(KAI_DIR),
        audio_wav=audio_path,
        background_png=BG_PATH,
        output=args.output,
        pose_cut_interval_s=2.0,
        transcript=SCRIPT,
    )
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
