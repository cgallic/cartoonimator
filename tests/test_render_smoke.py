"""End-to-end smoke test — renders a 1-second clip without external services.

Skipped unless ffmpeg is available. Does not require Rhubarb (uses fixed-flap
fallback). Verifies the pipeline assembles correctly: pose loading → mouth
overlay → composite → ffmpeg encode → audio mux.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from cartoonimator import load_mascot, render_scene

REPO_ROOT = Path(__file__).resolve().parents[1]
KAI_DIR = REPO_ROOT / "mascots" / "kai"
KAI_POSES = KAI_DIR / "poses"


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _kai_has_pngs() -> bool:
    if not KAI_POSES.is_dir():
        return False
    return any(KAI_POSES.glob("*.png"))


def _generate_silent_wav(out_path: Path, duration_s: float = 1.0) -> Path:
    """Make a 1-second silent WAV with ffmpeg (no Rhubarb needed)."""
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "anullsrc=channel_layout=mono:sample_rate=22050",
        "-t", f"{duration_s:.3f}",
        "-c:a", "pcm_s16le",
        str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0, f"ffmpeg failed: {proc.stderr[-300:]}"
    return out_path


def _generate_solid_bg(out_path: Path) -> Path:
    bg = Image.new("RGB", (1080, 1920), (20, 20, 40))
    bg.save(out_path)
    return out_path


@pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg/ffprobe not on PATH")
@pytest.mark.skipif(not _kai_has_pngs(), reason="Kai PNGs not present (run from full clone)")
def test_render_one_second_clip(tmp_path):
    audio = _generate_silent_wav(tmp_path / "silent.wav", duration_s=1.0)
    bg = _generate_solid_bg(tmp_path / "bg.png")
    out = tmp_path / "out.mp4"

    mascot = load_mascot(KAI_DIR)
    # Pick a single anchored pose so we don't render every state for every pose.
    anchored_pose = next(iter(mascot.poses_with_per_pose_anchors), None)
    assert anchored_pose, "no anchored poses in Kai mascot"

    render_scene(
        mascot=mascot,
        audio_wav=audio,
        background_png=bg,
        output=out,
        pose_ids=[anchored_pose],
        pose_cut_interval_s=2.0,
        insert_blink=False,  # 1s clip is below blink threshold anyway
    )

    assert out.is_file()
    # Verify dimensions + duration via ffprobe
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "stream=codec_type,width,height",
            "-show_entries", "format=duration",
            "-of", "json",
            str(out),
        ],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    assert video is not None
    assert video["width"] == 1080
    assert video["height"] == 1920
    duration = float(data["format"]["duration"])
    assert 0.7 < duration < 1.3  # ~1s with rounding tolerance
