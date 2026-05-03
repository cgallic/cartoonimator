"""Rhubarb Lip Sync wrapper — turn a WAV into a viseme timing track.

Rhubarb is a free CLI (https://github.com/DanielSWolf/rhubarb-lip-sync) that
maps WAV audio to Preston Blair phonemes (A-F + G/H/X). Production renders use
the 4-shape mouth set (closed/small/wide/round); the 2-shape collapse is kept
for legacy callers.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class VisemeCue:
    start_s: float
    end_s: float
    shape: str  # one of A/B/C/D/E/F/G/H/X (Preston Blair / Rhubarb)


# Map Rhubarb's 9 Preston-Blair shapes → 2 shapes (open/closed). Coarse —
# kept for legacy callers. New code should prefer MOUTH_SHAPE_MAP_4.
MOUTH_SHAPE_MAP_2 = {
    "X": "closed", "A": "closed", "F": "closed", "G": "closed",
    "B": "open", "C": "open", "D": "open", "E": "open", "H": "open",
}

# 9 → 4 mapping. The 4 states match MOUTH_SHAPES in face_overlay:
#   closed  — A, X (M/B/P, silence)
#   small   — B, F, G (K/S/T/N/D + V/F lip-tuck — slight parting)
#   wide    — C, D, H (AE/EH/AA + L tongue-visible — broad open)
#   round   — E       (AO/UR/UW — rounded "oh"/"oo")
MOUTH_SHAPE_MAP_4 = {
    "X": "closed",
    "A": "closed",
    "B": "small",
    "F": "small",
    "G": "small",
    "C": "wide",
    "D": "wide",
    "H": "wide",
    "E": "round",
}


class RhubarbError(RuntimeError):
    pass


def _find_rhubarb_binary() -> str:
    """Locate rhubarb on PATH, RHUBARB_BINARY env var, or common install paths."""
    env_path = os.environ.get("RHUBARB_BINARY")
    if env_path and Path(env_path).is_file():
        return env_path
    found = shutil.which("rhubarb")
    if found:
        return found
    for candidate in (
        "/usr/local/bin/rhubarb",
        "/opt/rhubarb/rhubarb",
        Path.home() / "bin" / "rhubarb",
    ):
        p = Path(candidate)
        if p.exists() and p.is_file():
            return str(p)
    raise RhubarbError(
        "rhubarb binary not found on PATH or common install paths. "
        "Install from https://github.com/DanielSWolf/rhubarb-lip-sync/releases "
        "or set the RHUBARB_BINARY env var."
    )


def viseme_track(
    wav_path: str | Path,
    transcript: str | None = None,
    rhubarb_binary: str | None = None,
) -> list[VisemeCue]:
    """Run Rhubarb on `wav_path`, return list of viseme cues.

    `transcript` is optional but improves accuracy when supplied — Rhubarb uses
    PocketSphinx for phoneme alignment when given the spoken text.
    """
    wav_path = Path(wav_path)
    if not wav_path.exists():
        raise RhubarbError(f"WAV not found: {wav_path}")

    binary = rhubarb_binary or _find_rhubarb_binary()

    out_json = wav_path.with_suffix(".rhubarb.json")
    cmd = [binary, "-f", "json", "-o", str(out_json), str(wav_path)]
    if transcript:
        transcript_file = wav_path.with_suffix(".transcript.txt")
        transcript_file.write_text(transcript, encoding="utf-8")
        cmd.extend(["-d", str(transcript_file)])

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RhubarbError(
            f"rhubarb exit {proc.returncode}: {(proc.stderr or '')[-400:]}"
        )

    data = json.loads(out_json.read_text(encoding="utf-8"))
    cues_raw = data.get("mouthCues", [])
    return [
        VisemeCue(
            start_s=float(c["start"]),
            end_s=float(c["end"]),
            shape=str(c["value"]),
        )
        for c in cues_raw
    ]


def _collapse(cues: list[VisemeCue], mapping: dict[str, str]) -> list[tuple[float, float, str]]:
    if not cues:
        return []
    out: list[tuple[float, float, str]] = []
    cur_start = cues[0].start_s
    cur_shape = mapping.get(cues[0].shape, "closed")
    cur_end = cues[0].end_s
    for c in cues[1:]:
        shape = mapping.get(c.shape, "closed")
        if shape == cur_shape:
            cur_end = c.end_s
        else:
            out.append((cur_start, cur_end, cur_shape))
            cur_start = c.start_s
            cur_shape = shape
            cur_end = c.end_s
    out.append((cur_start, cur_end, cur_shape))
    return out


def collapse_to_2_shapes(cues: list[VisemeCue]) -> list[tuple[float, float, str]]:
    """Legacy 9 → open/closed collapse."""
    return _collapse(cues, MOUTH_SHAPE_MAP_2)


def collapse_to_4_shapes(cues: list[VisemeCue]) -> list[tuple[float, float, str]]:
    """Preferred 9 → closed/small/wide/round collapse for the 4-state mouth library."""
    return _collapse(cues, MOUTH_SHAPE_MAP_4)


def smooth_timeline(
    segments: list[tuple[float, float, str]],
    min_hold_s: float = 0.070,
) -> list[tuple[float, float, str]]:
    """Merge any segment shorter than `min_hold_s` into its neighbor.

    At 30 fps, two frames is ~67 ms — a useful lower bound. Below that the eye
    reads "flicker" not "speech." Default 70 ms keeps Rhubarb detail while
    removing single-frame noise.
    """
    if not segments:
        return []
    out: list[list] = [list(segments[0])]
    for s, e, shape in segments[1:]:
        prev = out[-1]
        prev_dur = prev[1] - prev[0]
        cur_dur = e - s
        if cur_dur < min_hold_s and prev_dur >= min_hold_s and shape != prev[2]:
            prev[1] = e
            continue
        if cur_dur < min_hold_s and prev_dur < min_hold_s:
            prev[1] = e
            continue
        if shape == prev[2]:
            prev[1] = e
            continue
        out.append([s, e, shape])
    if len(out) > 1 and (out[-1][1] - out[-1][0]) < min_hold_s:
        out[-2][1] = out[-1][1]
        out.pop()
    return [(s, e, shape) for s, e, shape in out]
