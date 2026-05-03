"""Render a commercial-style scene with labeled beat cards.

Beat cards are large-text background slides that pair with each script segment.
Useful when a talking-head scene feels visually thin — beats give the viewer a
reading layer alongside the spoken script.

This example uses placeholder copy. Swap the BEATS list for your own.

Usage:
    python examples/beats_kaicalls.py voice.wav out.mp4
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from cartoonimator import load_mascot, render_scene

REPO_ROOT = Path(__file__).resolve().parents[1]
KAI_DIR = REPO_ROOT / "mascots" / "kai"


BEATS = [
    {"label": "AI ILLUSTRATES",       "sub": "one canonical body per pose"},
    {"label": "CODE ANIMATES",        "sub": "deterministic, no wobble"},
    {"label": "RHUBARB SYNCS",        "sub": "audio → mouth shapes"},
    {"label": "FFMPEG MUXES",         "sub": "voice and music"},
    {"label": "SHIP IT",              "sub": "one MP4 out"},
]


def _make_beat_card(label: str, sub: str, out_path: Path) -> Path:
    img = Image.new("RGB", (1080, 1920), (20, 20, 40))
    draw = ImageDraw.Draw(img)
    try:
        title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 96)
        sub_font = ImageFont.truetype("DejaVuSans.ttf", 56)
    except OSError:
        title_font = ImageFont.load_default()
        sub_font = ImageFont.load_default()
    # Title
    bbox = draw.textbbox((0, 0), label, font=title_font)
    tw = bbox[2] - bbox[0]
    draw.text(((1080 - tw) // 2, 240), label, fill=(255, 232, 132), font=title_font)
    # Subline
    bbox = draw.textbbox((0, 0), sub, font=sub_font)
    sw = bbox[2] - bbox[0]
    draw.text(((1080 - sw) // 2, 380), sub, fill=(220, 220, 240), font=sub_font)
    img.save(out_path, "PNG")
    return out_path


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("audio", help="path to spoken WAV/MP3")
    p.add_argument("output", help="path to output MP4")
    args = p.parse_args()

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # Use the first beat as the scene background. For a true beat-card
        # commercial, render N separate scenes (one per beat) and concat.
        bg = _make_beat_card(BEATS[0]["label"], BEATS[0]["sub"], tmp / "bg.png")

        out = render_scene(
            mascot=load_mascot(KAI_DIR),
            audio_wav=args.audio,
            background_png=bg,
            output=args.output,
            pose_cut_interval_s=2.0,
        )
        print(f"wrote {out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
