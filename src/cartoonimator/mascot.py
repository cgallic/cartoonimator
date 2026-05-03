"""High-level render API — turn a mascot + audio WAV + background into an MP4.

This is the headline `render_scene` function. It's audio-first: you supply a
WAV (record yourself, use any TTS, or use one of the bundled providers in
`cartoonimator.tts`). Rhubarb aligns it to visemes; we render mouth states
on each pose; FFmpeg muxes the result.
"""
from __future__ import annotations

import logging
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path

from .face_overlay import load_anchors, render_face_state
from .lipsync import (
    RhubarbError,
    collapse_to_4_shapes,
    smooth_timeline,
    viseme_track,
)
from .mascot_loader import Mascot, load_mascot
from .scene import SceneAudio, Shot, render_shots

log = logging.getLogger(__name__)

DEFAULT_POSE_CUT_INTERVAL_S = 2.0
DEFAULT_MOUTH_MIN_HOLD_S = 0.070
DEFAULT_BLINK_DURATION_S = 0.10
DEFAULT_BLINK_THRESHOLD_S = 3.0
DEFAULT_FLAP_PERIOD_S = 0.13
DEFAULT_MUSIC_VOLUME = 0.18
DEFAULT_FPS = 30


def _audio_duration_s(audio_path: Path) -> float:
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {audio_path}: {proc.stderr[-300:]}")
    return float((proc.stdout or "0").strip())


def _lipsync_wav(audio_path: Path, workdir: Path) -> Path:
    """Convert any audio file to a mono 16kHz WAV that Rhubarb aligns reliably."""
    output = workdir / "voice_lipsync.wav"
    proc = subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(audio_path),
            "-ac", "1",
            "-ar", "16000",
            "-vn",
            str(output),
        ],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg lipsync WAV conversion failed: {(proc.stderr or '')[-400:]}"
        )
    return output


def _merge_adjacent(
    segments: list[tuple[float, float, str]],
) -> list[tuple[float, float, str]]:
    merged: list[tuple[float, float, str]] = []
    for start, end, shape in segments:
        if end <= start:
            continue
        if merged and merged[-1][2] == shape and abs(start - merged[-1][1]) < 1e-3:
            prev_start, _, _ = merged[-1]
            merged[-1] = (prev_start, end, shape)
        else:
            merged.append((start, end, shape))
    return merged


def _normalize_mouth_timeline(
    segments: list[tuple[float, float, str]],
    duration_s: float,
) -> list[tuple[float, float, str]]:
    """Clip Rhubarb segments to the audio duration and fill gaps with closed."""
    if duration_s <= 0:
        return []

    out: list[tuple[float, float, str]] = []
    cursor = 0.0
    for start, end, shape in sorted(segments, key=lambda item: item[0]):
        start = max(0.0, min(duration_s, start))
        end = max(0.0, min(duration_s, end))
        if end <= start:
            continue
        if start > cursor + 1e-3:
            out.append((cursor, start, "closed"))
        start = max(start, cursor)
        if end > start + 1e-3:
            out.append((start, end, shape))
            cursor = end
    if cursor < duration_s - 1e-3:
        out.append((cursor, duration_s, "closed"))
    return _merge_adjacent(out)


def _build_lipsynced_talking_segment(
    mouth_timeline: list[tuple[float, float, str]],
    mouth_pngs: dict[str, Path],
    bg_path: Path,
    window_start_s: float,
    duration_s: float,
    scale: float,
    anchor: str,
) -> list[Shot]:
    if duration_s <= 1e-3:
        return []

    window_end_s = window_start_s + duration_s
    shots: list[Shot] = []
    cursor = window_start_s

    for start, end, shape in mouth_timeline:
        if end <= window_start_s or start >= window_end_s:
            continue
        clipped_start = max(start, window_start_s)
        clipped_end = min(end, window_end_s)
        if clipped_start > cursor + 1e-3:
            shots.append(Shot(
                pose_path=mouth_pngs["closed"], bg_path=bg_path,
                duration_s=clipped_start - cursor, scale=scale, anchor=anchor,
            ))
        if clipped_end > clipped_start + 1e-3:
            shots.append(Shot(
                pose_path=mouth_pngs.get(shape, mouth_pngs["closed"]),
                bg_path=bg_path,
                duration_s=clipped_end - clipped_start,
                scale=scale,
                anchor=anchor,
            ))
            cursor = clipped_end

    if cursor < window_end_s - 1e-3:
        shots.append(Shot(
            pose_path=mouth_pngs["closed"], bg_path=bg_path,
            duration_s=window_end_s - cursor, scale=scale, anchor=anchor,
        ))
    return shots


def _build_fixed_talking_segment(
    mouth_pngs: dict[str, Path],
    bg_path: Path,
    duration_s: float,
    scale: float,
    anchor: str,
    flap_period_s: float = DEFAULT_FLAP_PERIOD_S,
) -> list[Shot]:
    """Fallback if Rhubarb is unavailable: a simple 4-state cartoon flap."""
    if duration_s <= 1e-3:
        return []
    shapes = ("closed", "small", "wide", "small")
    shots: list[Shot] = []
    elapsed = 0.0
    index = 0
    while elapsed < duration_s - 1e-3:
        shot_dur = min(flap_period_s, duration_s - elapsed)
        shape = shapes[index % len(shapes)]
        shots.append(Shot(
            pose_path=mouth_pngs[shape], bg_path=bg_path,
            duration_s=shot_dur, scale=scale, anchor=anchor,
        ))
        elapsed += shot_dur
        index += 1
    return shots


def _build_talking_window(
    mouth_timeline: list[tuple[float, float, str]] | None,
    mouth_pngs: dict[str, Path],
    bg_path: Path,
    window_start_s: float,
    duration_s: float,
    scale: float,
    anchor: str,
) -> list[Shot]:
    if mouth_timeline:
        return _build_lipsynced_talking_segment(
            mouth_timeline=mouth_timeline,
            mouth_pngs=mouth_pngs,
            bg_path=bg_path,
            window_start_s=window_start_s,
            duration_s=duration_s,
            scale=scale,
            anchor=anchor,
        )
    return _build_fixed_talking_segment(
        mouth_pngs=mouth_pngs,
        bg_path=bg_path,
        duration_s=duration_s,
        scale=scale,
        anchor=anchor,
    )


def _render_pose_mouth_sets(
    mascot: Mascot,
    pose_ids: Sequence[str],
    workdir: Path,
) -> tuple[dict[str, dict[str, Path]], dict[str, Path]]:
    """Pre-render every mouth state on every selected pose.

    Anchors are loaded with `pose_id`, so the mouth is patched/drawn in that
    pose's own face box instead of the canonical default face box. Important
    for tilted-head poses.
    """
    mouth_sets: dict[str, dict[str, Path]] = {}
    blink_for_mouth_png: dict[str, Path] = {}

    for pose_id in pose_ids:
        pose_png = mascot.pose_path(pose_id)
        anchors = load_anchors(mascot.anchors_path, pose_id=pose_id)
        pose_mouths = {
            shape: render_face_state(
                pose_png,
                anchors,
                mouth=shape,
                eyes="open",
                output_path=workdir / f"{pose_id}_{shape}.png",
            )
            for shape in ("closed", "small", "wide", "round")
        }
        blink_png = render_face_state(
            pose_png,
            anchors,
            mouth="closed",
            eyes="closed",
            output_path=workdir / f"{pose_id}_blink.png",
        )
        for mouth_png in pose_mouths.values():
            blink_for_mouth_png[str(mouth_png)] = blink_png
        mouth_sets[pose_id] = pose_mouths

    return mouth_sets, blink_for_mouth_png


def _build_pose_cut_talking_segment(
    mouth_timeline: list[tuple[float, float, str]] | None,
    pose_mouth_sets: dict[str, dict[str, Path]],
    bg_path: Path,
    window_start_s: float,
    duration_s: float,
    scale: float,
    anchor: str,
    pose_cut_interval_s: float = DEFAULT_POSE_CUT_INTERVAL_S,
) -> list[Shot]:
    if duration_s <= 1e-3:
        return []
    pose_ids = list(pose_mouth_sets)
    if not pose_ids:
        raise ValueError("pose_mouth_sets must include at least one pose")

    shots: list[Shot] = []
    cursor = window_start_s
    end_s = window_start_s + duration_s
    pose_index = 0
    hold_s = max(0.5, pose_cut_interval_s)

    while cursor < end_s - 1e-3:
        segment_dur = min(hold_s, end_s - cursor)
        pose_id = pose_ids[pose_index % len(pose_ids)]
        shots.extend(_build_talking_window(
            mouth_timeline=mouth_timeline,
            mouth_pngs=pose_mouth_sets[pose_id],
            bg_path=bg_path,
            window_start_s=cursor,
            duration_s=segment_dur,
            scale=scale,
            anchor=anchor,
        ))
        cursor += segment_dur
        pose_index += 1

    return shots


def _insert_pose_matched_blink(
    shots: list[Shot],
    blink_for_mouth_png: dict[str, Path],
    blink_at_s: float,
    blink_duration_s: float = DEFAULT_BLINK_DURATION_S,
) -> list[Shot]:
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
                pose_path=shot.pose_path,
                bg_path=shot.bg_path,
                duration_s=before_d,
                scale=shot.scale,
                anchor=shot.anchor,
            ))
        out.append(Shot(
            pose_path=blink_for_mouth_png.get(str(shot.pose_path), shot.pose_path),
            bg_path=shot.bg_path,
            duration_s=blink_duration_s,
            scale=shot.scale,
            anchor=shot.anchor,
        ))
        if after_d > 1e-3:
            out.append(Shot(
                pose_path=shot.pose_path,
                bg_path=shot.bg_path,
                duration_s=after_d,
                scale=shot.scale,
                anchor=shot.anchor,
            ))
        elapsed += shot.duration_s
        inserted = True
    return out


def _select_pose_ids(
    mascot: Mascot,
    requested_pose_ids: Sequence[str] | None,
) -> list[str]:
    """Pick the pose pool, preferring poses that have per-pose anchors tagged."""
    if requested_pose_ids:
        return [pid for pid in requested_pose_ids if pid in mascot.pose_files]

    if mascot.poses_with_per_pose_anchors:
        return [pid for pid in mascot.pose_ids if mascot.has_per_pose_anchor(pid)]
    return list(mascot.pose_ids)


def render_scene(
    mascot: Mascot | str | Path,
    audio_wav: str | Path,
    background_png: str | Path,
    output: str | Path,
    pose_ids: Sequence[str] | None = None,
    pose_cut_interval_s: float = DEFAULT_POSE_CUT_INTERVAL_S,
    music_track: str | Path | None = None,
    music_volume: float = DEFAULT_MUSIC_VOLUME,
    insert_blink: bool = True,
    transcript: str | None = None,
    scale: float = 0.85,
    anchor: str = "center-bottom",
    fps: int = DEFAULT_FPS,
) -> Path:
    """Render an animated mascot scene → MP4 at `output`.

    Args:
        mascot: a Mascot instance, or a path to a mascot directory (loaded automatically)
        audio_wav: path to spoken audio (WAV preferred; MP3 also accepted, gets downconverted)
        background_png: path to a 1080×1920 background PNG
        output: where to write the final MP4
        pose_ids: explicit pose pool to cycle through; defaults to all poses with per-pose anchors
        pose_cut_interval_s: how often to cut to the next pose during speech (default 2.0s)
        music_track: optional background music; ducked under voice
        music_volume: music level under voice (0-1)
        insert_blink: insert a blink halfway through if the scene is ≥ 3s
        transcript: optional spoken text — improves Rhubarb alignment when supplied
        scale: pose height as fraction of canvas height
        anchor: where to anchor the pose ("center-bottom", "center", "left-bottom", "right-bottom")
        fps: output frame rate

    Returns:
        Path to the rendered MP4.
    """
    if isinstance(mascot, Mascot):
        loaded: Mascot = mascot
    else:
        loaded = load_mascot(mascot)

    audio_path = Path(audio_wav)
    bg_path = Path(background_png)
    output = Path(output)

    if not audio_path.exists():
        raise FileNotFoundError(f"audio not found: {audio_path}")
    if not bg_path.exists():
        raise FileNotFoundError(f"background not found: {bg_path}")

    selected_pose_ids = _select_pose_ids(loaded, pose_ids)
    if not selected_pose_ids:
        raise ValueError(
            f"mascot {loaded.name!r} has no usable poses "
            f"(check anchors.json has per_pose entries or pass explicit pose_ids)"
        )

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        audio_dur = _audio_duration_s(audio_path)
        if audio_dur <= 0:
            raise ValueError(f"audio at {audio_path} has zero duration")

        pose_mouth_sets, blink_for_mouth_png = _render_pose_mouth_sets(
            mascot=loaded,
            pose_ids=selected_pose_ids,
            workdir=tmp,
        )

        mouth_timeline: list[tuple[float, float, str]] | None = None
        try:
            cues = viseme_track(
                _lipsync_wav(audio_path, tmp),
                transcript=transcript,
            )
            mouth_timeline = _normalize_mouth_timeline(
                smooth_timeline(
                    collapse_to_4_shapes(cues),
                    min_hold_s=DEFAULT_MOUTH_MIN_HOLD_S,
                ),
                audio_dur,
            )
        except (RhubarbError, RuntimeError, OSError) as exc:
            log.warning("rhubarb lipsync unavailable; falling back to fixed flap: %s", exc)

        shots = _build_pose_cut_talking_segment(
            mouth_timeline=mouth_timeline,
            pose_mouth_sets=pose_mouth_sets,
            bg_path=bg_path,
            window_start_s=0.0,
            duration_s=audio_dur,
            scale=scale,
            anchor=anchor,
            pose_cut_interval_s=pose_cut_interval_s,
        )

        if insert_blink:
            total_dur = sum(s.duration_s for s in shots)
            if total_dur >= DEFAULT_BLINK_THRESHOLD_S:
                shots = _insert_pose_matched_blink(
                    shots,
                    blink_for_mouth_png=blink_for_mouth_png,
                    blink_at_s=total_dur * 0.5,
                    blink_duration_s=DEFAULT_BLINK_DURATION_S,
                )

        scene_audio = SceneAudio(
            voice_wav=audio_path,
            music_track=Path(music_track) if music_track else None,
            music_volume=music_volume,
        )
        render_shots(shots, scene_audio, output, fps=fps)

    return output
