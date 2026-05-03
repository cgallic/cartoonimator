"""Stop-motion compositor — the cartoon-animator core.

Turns a list of timed Shots (each one a character PNG + bg PNG + hold duration)
into a 1080x1920 30fps MP4 with voice + music mixed in. Zero diffusion in the
loop, so no AI artifacts.

Caller is responsible for building the Shot list — typically via the high-level
`mascot.render_scene` which converts an audio WAV + Rhubarb visemes into Shots.
"""
from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .composite import composite_scene

CANVAS_W = 1080
CANVAS_H = 1920
DEFAULT_FPS = 30


@dataclass
class Shot:
    """One held frame in the stop-motion timeline."""
    pose_path: Path
    bg_path: Path
    duration_s: float
    scale: float = 0.85
    anchor: str = "center-bottom"


@dataclass
class SceneAudio:
    """Audio inputs for the scene."""
    voice_wav: Path | None = None      # optional spoken VO
    music_track: Path | None = None    # optional bg music
    music_volume: float = 0.30          # music level under voice
    music_only_volume: float = 0.75     # music level when there's no voice


def _render_shot_clip(
    composite_png: Path, duration_s: float, fps: int, output_mp4: Path
) -> Path:
    """Loop a single PNG for `duration_s` into a silent mp4 at `fps`."""
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(composite_png),
        "-t", f"{duration_s:.3f}",
        "-r", str(fps),
        "-pix_fmt", "yuv420p",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-vf", f"scale={CANVAS_W}:{CANVAS_H}:flags=lanczos",
        str(output_mp4),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg shot render failed (exit {proc.returncode}). "
            f"stderr tail: {(proc.stderr or '')[-500:]}"
        )
    return output_mp4


def _concat_clips(clip_paths: list[Path], output_mp4: Path, workdir: Path) -> Path:
    """Concat-demux a list of mp4s into one. All must share codec/params."""
    list_file = workdir / "concat.txt"
    list_file.write_text(
        "\n".join(f"file '{p.as_posix()}'" for p in clip_paths) + "\n",
        encoding="utf-8",
    )
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        str(output_mp4),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg concat failed (exit {proc.returncode}). "
            f"stderr tail: {(proc.stderr or '')[-500:]}"
        )
    return output_mp4


def _mux_audio(silent_video: Path, audio: SceneAudio, output: Path) -> Path:
    """Mux voice + music (or music alone) onto a silent video."""
    if audio.voice_wav and audio.music_track:
        cmd = [
            "ffmpeg", "-y",
            "-i", str(silent_video),
            "-i", str(audio.voice_wav),
            "-stream_loop", "-1", "-i", str(audio.music_track),
            "-filter_complex",
            f"[2:a]volume={audio.music_volume}[m];"
            f"[1:a][m]amix=inputs=2:duration=first:dropout_transition=0[a]",
            "-map", "0:v", "-map", "[a]",
            "-c:v", "copy",
            "-shortest",
            str(output),
        ]
    elif audio.voice_wav:
        cmd = [
            "ffmpeg", "-y",
            "-i", str(silent_video),
            "-i", str(audio.voice_wav),
            "-map", "0:v", "-map", "1:a",
            "-c:v", "copy",
            "-shortest",
            str(output),
        ]
    elif audio.music_track:
        cmd = [
            "ffmpeg", "-y",
            "-i", str(silent_video),
            "-stream_loop", "-1", "-i", str(audio.music_track),
            "-filter_complex", f"[1:a]volume={audio.music_only_volume}[a]",
            "-map", "0:v", "-map", "[a]",
            "-c:v", "copy",
            "-shortest",
            str(output),
        ]
    else:
        cmd = ["ffmpeg", "-y", "-i", str(silent_video), "-c", "copy", str(output)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg mux failed (exit {proc.returncode}). "
            f"stderr tail: {(proc.stderr or '')[-500:]}"
        )
    return output


def render_shots(
    shots: list[Shot],
    audio: SceneAudio,
    output: Path,
    fps: int = DEFAULT_FPS,
) -> Path:
    """Render a list of Shots → final MP4 at `output`.

    Pipeline: composite each shot's pose-on-bg → loop-encode for shot.duration_s
    → concat all → mux audio. No diffusion anywhere.
    """
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if not shots:
        raise ValueError("render_shots requires at least one shot")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        clip_paths: list[Path] = []
        for i, shot in enumerate(shots):
            composite_png = tmp / f"composite_{i:03d}.png"
            composite_scene(
                bg_path=shot.bg_path,
                pose_path=shot.pose_path,
                scale=shot.scale,
                anchor=shot.anchor,
                output_path=composite_png,
            )
            clip = tmp / f"shot_{i:03d}.mp4"
            _render_shot_clip(composite_png, shot.duration_s, fps, clip)
            clip_paths.append(clip)

        silent = tmp / "silent.mp4"
        _concat_clips(clip_paths, silent, tmp)
        _mux_audio(silent, audio, output)

    return output


# ─── Helpers for building Shot timelines ─────────────────────────────────────


def build_talking_segment(
    talking_closed_png: Path,
    talking_open_png: Path,
    bg_path: Path,
    duration_s: float,
    flap_period_s: float = 0.13,
    scale: float = 0.85,
    anchor: str = "center-bottom",
) -> list[Shot]:
    """Build a sequence of alternating closed/open mouth shots for `duration_s`.

    flap_period_s defaults to ~7.7 Hz which matches typical English syllable
    rate (4-7 Hz) with slight overshoot for that "lively cartoon flap" feel.
    Used as a fallback when Rhubarb isn't available.
    """
    shots: list[Shot] = []
    elapsed = 0.0
    use_open = False
    while elapsed < duration_s - 1e-3:
        d = min(flap_period_s, duration_s - elapsed)
        png = talking_open_png if use_open else talking_closed_png
        shots.append(Shot(
            pose_path=png, bg_path=bg_path,
            duration_s=d, scale=scale, anchor=anchor,
        ))
        elapsed += d
        use_open = not use_open
    return shots


def insert_blink(
    shots: list[Shot],
    talking_blink_png: Path,
    blink_at_s: float,
    blink_duration_s: float = 0.10,
) -> list[Shot]:
    """Splice a single blink-frame Shot into an existing timeline at `blink_at_s`.
    Returns a new list. The shot at that time is split if needed.
    """
    out: list[Shot] = []
    elapsed = 0.0
    inserted = False
    for shot in shots:
        if inserted or blink_at_s >= elapsed + shot.duration_s:
            out.append(shot)
            elapsed += shot.duration_s
            continue
        before_d = blink_at_s - elapsed
        after_d = shot.duration_s - before_d - blink_duration_s
        if before_d > 1e-3:
            out.append(Shot(
                pose_path=shot.pose_path, bg_path=shot.bg_path,
                duration_s=before_d, scale=shot.scale, anchor=shot.anchor,
            ))
        out.append(Shot(
            pose_path=talking_blink_png, bg_path=shot.bg_path,
            duration_s=blink_duration_s, scale=shot.scale, anchor=shot.anchor,
        ))
        if after_d > 1e-3:
            out.append(Shot(
                pose_path=shot.pose_path, bg_path=shot.bg_path,
                duration_s=after_d, scale=shot.scale, anchor=shot.anchor,
            ))
        elapsed += shot.duration_s
        inserted = True
    return out
