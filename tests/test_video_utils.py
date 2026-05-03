"""Smoke tests for ffmpeg helpers — skipped if ffmpeg is unavailable."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from cartoonimator import cut_window, mix_music


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _ffprobe_duration(path: Path) -> float:
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json", str(path),
        ],
        capture_output=True, text=True,
    )
    return float(json.loads(proc.stdout)["format"]["duration"])


def _make_video(out_path: Path, duration_s: float = 4.0, with_audio: bool = True) -> Path:
    if with_audio:
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c=blue:s=320x240:d={duration_s:.3f}",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration_s:.3f}",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "96k",
            "-shortest",
            str(out_path),
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c=red:s=320x240:d={duration_s:.3f}",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            str(out_path),
        ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-300:]
    return out_path


def _make_silent_wav(out_path: Path, duration_s: float = 5.0) -> Path:
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "anullsrc=channel_layout=mono:sample_rate=22050",
        "-t", f"{duration_s:.3f}",
        "-c:a", "pcm_s16le",
        str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0
    return out_path


def test_cut_window_rejects_invalid_range(tmp_path):
    src = tmp_path / "src.mp4"
    if _has_ffmpeg():
        _make_video(src, duration_s=2.0, with_audio=False)
    else:
        src.touch()
    with pytest.raises(ValueError):
        cut_window(src, start_s=1.0, end_s=0.5, out_path=tmp_path / "out.mp4")


@pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg/ffprobe not on PATH")
def test_cut_window_extracts_subrange(tmp_path):
    src = _make_video(tmp_path / "src.mp4", duration_s=4.0)
    out = cut_window(src, start_s=1.0, end_s=2.5, out_path=tmp_path / "out.mp4")
    duration = _ffprobe_duration(out)
    assert 1.3 < duration < 1.7


@pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg/ffprobe not on PATH")
def test_mix_music_with_audio(tmp_path):
    video = _make_video(tmp_path / "video.mp4", duration_s=2.0, with_audio=True)
    music = _make_silent_wav(tmp_path / "music.wav", duration_s=5.0)
    out = mix_music(video, music, tmp_path / "out.mp4", volume=0.2)
    assert out.is_file()
    # Output should still be ~2s (video duration); music looped to fit
    duration = _ffprobe_duration(out)
    assert 1.7 < duration < 2.3


@pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg/ffprobe not on PATH")
def test_mix_music_silent_video(tmp_path):
    video = _make_video(tmp_path / "video.mp4", duration_s=2.0, with_audio=False)
    music = _make_silent_wav(tmp_path / "music.wav", duration_s=5.0)
    out = mix_music(video, music, tmp_path / "out.mp4", volume=0.5)
    assert out.is_file()
