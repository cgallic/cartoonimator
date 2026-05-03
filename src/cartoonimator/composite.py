"""PIL pose-on-background compositor for mascot scenes."""
from __future__ import annotations

import tempfile
from pathlib import Path

from PIL import Image

CANVAS_W = 1080
CANVAS_H = 1920
_VALID_ANCHORS = {"center-bottom", "center", "left-bottom", "right-bottom"}


def composite_scene(
    bg_path: str | Path,
    pose_path: str | Path,
    scale: float = 0.85,
    anchor: str = "center-bottom",
    output_path: str | Path | None = None,
) -> Path:
    """Paste pose (transparent PNG) onto bg (1080x1920 PNG). Returns output path."""
    if anchor not in _VALID_ANCHORS:
        raise ValueError(f"anchor must be one of {_VALID_ANCHORS}; got {anchor!r}")

    bg = Image.open(bg_path).convert("RGBA")
    if bg.size != (CANVAS_W, CANVAS_H):
        bg = bg.resize((CANVAS_W, CANVAS_H), Image.Resampling.LANCZOS)

    pose = Image.open(pose_path).convert("RGBA")
    target_h = int(CANVAS_H * scale)
    target_w = int(pose.size[0] * (target_h / pose.size[1]))
    pose_scaled = pose.resize((target_w, target_h), Image.Resampling.LANCZOS)

    if anchor == "center-bottom":
        x = (CANVAS_W - target_w) // 2
        y = CANVAS_H - target_h
    elif anchor == "center":
        x = (CANVAS_W - target_w) // 2
        y = (CANVAS_H - target_h) // 2
    elif anchor == "left-bottom":
        x = 0
        y = CANVAS_H - target_h
    elif anchor == "right-bottom":
        x = CANVAS_W - target_w
        y = CANVAS_H - target_h
    else:
        raise ValueError(f"unhandled anchor {anchor!r}")

    bg.alpha_composite(pose_scaled, dest=(x, y))

    if output_path is None:
        output_path = Path(tempfile.mkstemp(suffix=".png")[1])
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    bg.convert("RGB").save(output_path, "PNG")
    return output_path
