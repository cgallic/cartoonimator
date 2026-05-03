"""cartoonimator — AI illustrates, code animates.

Public API:

    from cartoonimator import load_mascot, render_scene
    from cartoonimator.tts import ElevenLabsProvider, MossProvider, BYOProvider
"""
from __future__ import annotations

from .face_overlay import MOUTH_SHAPES, FaceAnchors, load_anchors, render_face_state
from .lipsync import (
    MOUTH_SHAPE_MAP_2,
    MOUTH_SHAPE_MAP_4,
    RhubarbError,
    VisemeCue,
    collapse_to_2_shapes,
    collapse_to_4_shapes,
    smooth_timeline,
    viseme_track,
)
from .mascot import render_scene
from .mascot_loader import Mascot, load_mascot
from .scene import (
    SceneAudio,
    Shot,
    build_talking_segment,
    insert_blink,
    render_shots,
)
from .video_utils import cut_window, mix_music

__version__ = "0.1.0"

__all__ = [
    # high-level API
    "render_scene",
    "load_mascot",
    "Mascot",
    # mid-level
    "render_shots",
    "Shot",
    "SceneAudio",
    "build_talking_segment",
    "insert_blink",
    # face overlays
    "FaceAnchors",
    "MOUTH_SHAPES",
    "load_anchors",
    "render_face_state",
    # lipsync
    "VisemeCue",
    "viseme_track",
    "collapse_to_2_shapes",
    "collapse_to_4_shapes",
    "smooth_timeline",
    "MOUTH_SHAPE_MAP_2",
    "MOUTH_SHAPE_MAP_4",
    "RhubarbError",
    # video utils
    "mix_music",
    "cut_window",
    # version
    "__version__",
]
