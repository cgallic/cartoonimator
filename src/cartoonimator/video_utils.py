"""Generic FFmpeg helpers for trimming video and mixing music.

These are not used internally by `render_scene` (which handles voice + music
in one pass). They're for post-processing workflows: take an existing MP4,
add music after the fact, or extract a window for a clip.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


def cut_window(
    source_path: str | Path,
    start_s: float,
    end_s: float,
    out_path: str | Path,
    crf: int = 18,
    preset: str = "fast",
) -> Path:
    """Extract `[start_s, end_s]` from `source_path` into `out_path`.

    Re-encodes with libx264 + aac (so the output is seekable and key-framed
    correctly even when the source isn't). For a stream-copy version, do it
    yourself with `-c copy` — that's faster but won't slice precisely.
    """
    duration = end_s - start_s
    if duration <= 0:
        raise ValueError(f"end_s ({end_s}) must be > start_s ({start_s})")

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start_s:.3f}",
        "-i", str(source_path),
        "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg cut_window failed (exit {proc.returncode}). "
            f"stderr tail: {(proc.stderr or '<empty>')[-800:]}"
        )
    return out


def _video_has_audio(path: str | Path) -> bool:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    return "audio" in (proc.stdout or "")


def mix_music(
    video: str | Path,
    music: str | Path,
    output: str | Path,
    volume: float = 0.15,
) -> Path:
    """Mix `music` under `video`'s audio at `volume` (0–1). Looped to video duration.

    If `video` has no audio stream, `music` becomes the sole audio at `volume`
    (no mixing). The video stream is copied — only the audio is re-encoded.
    """
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    if _video_has_audio(video):
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video),
            "-stream_loop", "-1", "-i", str(music),
            "-filter_complex",
            f"[1:a]volume={volume}[m];[0:a][m]amix=inputs=2:duration=first:dropout_transition=0",
            "-c:v", "copy",
            "-shortest",
            str(out),
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video),
            "-stream_loop", "-1", "-i", str(music),
            "-filter_complex", f"[1:a]volume={volume}[a]",
            "-map", "0:v", "-map", "[a]",
            "-c:v", "copy",
            "-shortest",
            str(out),
        ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg mix_music failed (exit {proc.returncode}). "
            f"stderr tail: {(proc.stderr or '<empty>')[-800:]}"
        )
    return out
