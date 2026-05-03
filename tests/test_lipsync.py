"""Viseme collapse + smoothing tests — no Rhubarb required."""
from __future__ import annotations

from cartoonimator.lipsync import (
    VisemeCue,
    collapse_to_2_shapes,
    collapse_to_4_shapes,
    smooth_timeline,
)


def _cue(start, end, shape):
    return VisemeCue(start_s=start, end_s=end, shape=shape)


def test_collapse_4_shapes_basic():
    cues = [
        _cue(0.0, 0.1, "X"),
        _cue(0.1, 0.3, "B"),
        _cue(0.3, 0.5, "C"),
        _cue(0.5, 0.6, "E"),
        _cue(0.6, 0.7, "X"),
    ]
    out = collapse_to_4_shapes(cues)
    shapes = [s for _, _, s in out]
    assert shapes == ["closed", "small", "wide", "round", "closed"]


def test_collapse_4_shapes_merges_adjacent_same():
    cues = [
        _cue(0.0, 0.1, "X"),
        _cue(0.1, 0.2, "A"),  # both → closed
        _cue(0.2, 0.4, "B"),
    ]
    out = collapse_to_4_shapes(cues)
    assert len(out) == 2
    assert out[0] == (0.0, 0.2, "closed")
    assert out[1] == (0.2, 0.4, "small")


def test_collapse_2_shapes():
    cues = [
        _cue(0.0, 0.1, "A"),
        _cue(0.1, 0.3, "C"),
        _cue(0.3, 0.4, "X"),
    ]
    out = collapse_to_2_shapes(cues)
    shapes = [s for _, _, s in out]
    assert shapes == ["closed", "open", "closed"]


def test_smooth_timeline_drops_short_flicker():
    segments = [
        (0.0, 0.5, "closed"),
        (0.5, 0.51, "wide"),  # 10ms — way under 70ms threshold
        (0.51, 1.0, "closed"),
    ]
    out = smooth_timeline(segments, min_hold_s=0.070)
    # The wide flicker should be absorbed
    shapes = [s for _, _, s in out]
    assert "wide" not in shapes
    assert out[-1][1] == 1.0


def test_smooth_empty():
    assert smooth_timeline([]) == []
