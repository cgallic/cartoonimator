"""Face overlay drawing — mouth flap + eye blink on a locked pose PNG.

This is the "code-as-animator" layer: AI generates ONE canonical body per pose,
this module draws mouth/eye states on top using PIL primitives at hardcoded
anchor coordinates (anchors.json). The body never changes pixels between
talking frames, so there's zero scaling/framing wobble.

Mouth states:
- closed = curved smile stroke matching the mascot's drawn mouth language
- small/wide = shallow crescent openings
- round = oval O for surprise/oo sounds
- The source mouth is patched out with sampled skin color before replacement
  so the original drawn mouth cannot peek through.

Eye states:
- Open eyes = pose PNG as-is.
- Closed eyes (blink) = thin horizontal lines at left/right_eye anchors.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

# Draw face overlays supersampled, then downsample. PIL polygons/lines are
# otherwise hard-aliased, which makes small mouth changes look pixelated.
OVERLAY_AA_SCALE = 4

# Patch dimensions — generous so the source's drawn mouth (smile line, oval,
# or side dash) is fully erased before we draw our overlay.
MOUTH_PATCH_PAD_W = 36
MOUTH_PATCH_PAD_H = 28

# Mouth state shape multipliers (relative to anchor.mouth_open_w / open_h).
# Modeled from a stylized cartoon mascot — adjust per character if your art
# style needs different proportions.
MOUTH_SHAPES = {
    "closed": {"w_mult": 0.69, "h_mult": 0.38, "kind": "smile"},
    "small":  {"w_mult": 0.48, "h_mult": 0.36, "kind": "crescent"},
    "wide":   {"w_mult": 0.69, "h_mult": 0.72, "kind": "crescent"},
    "round":  {"w_mult": 0.24, "h_mult": 0.68, "kind": "round"},
}

@dataclass
class FaceAnchors:
    image_size: tuple[int, int]
    mouth_cx: int
    mouth_cy: int
    mouth_open_w: int
    mouth_open_h: int
    mouth_box: tuple[int, int, int, int] | None
    left_eye_cx: int
    left_eye_cy: int
    left_eye_w: int
    left_eye_h: int
    right_eye_cx: int
    right_eye_cy: int
    right_eye_w: int
    right_eye_h: int
    outline_color: tuple[int, int, int, int]


def _from_dict(image_size: tuple[int, int], mouth: dict, le: dict, re: dict,
               outline_color: list[int]) -> FaceAnchors:
    box = mouth.get("box") if mouth else None
    mouth_box = None
    if isinstance(box, dict):
        mouth_box = (
            int(box["x"]), int(box["y"]),
            int(box["w"]), int(box["h"]),
        )
    return FaceAnchors(
        image_size=image_size,
        mouth_cx=int(mouth["cx"]), mouth_cy=int(mouth["cy"]),
        mouth_open_w=int(mouth["open_w"]), mouth_open_h=int(mouth["open_h"]),
        mouth_box=mouth_box,
        left_eye_cx=int(le["cx"]), left_eye_cy=int(le["cy"]),
        left_eye_w=int(le["w"]), left_eye_h=int(le["h"]),
        right_eye_cx=int(re["cx"]), right_eye_cy=int(re["cy"]),
        right_eye_w=int(re["w"]), right_eye_h=int(re["h"]),
        outline_color=tuple(outline_color),  # type: ignore[arg-type]
    )


def load_anchors(anchors_path: str | Path, pose_id: str | None = None) -> FaceAnchors:
    """Load anchors for a given pose. Supports both schema versions:

    v1 (flat): {image_size, mouth, left_eye, right_eye, outline_color}
       — used as universal anchors regardless of pose_id.

    v2 (per-pose): {image_size, default: {...}, per_pose: {pose_id: {...}}}
       — pose_id lookup falls back to default.

    If pose_id is given and v2 has a per-pose entry for it, that wins.
    Otherwise the default (or v1 root) anchors are returned. Per-pose entries
    inherit the default's outline_color and any size dimensions they don't
    override.
    """
    data = json.loads(Path(anchors_path).read_text(encoding="utf-8"))
    image_size = tuple(data.get("image_size", [1024, 1024]))  # type: ignore[arg-type]

    if "per_pose" in data or "default" in data:
        default = data.get("default", {})
        outline = default.get("outline_color", [26, 26, 46, 255])
        if pose_id and pose_id in data.get("per_pose", {}):
            entry = data["per_pose"][pose_id]
            mouth = {**default.get("mouth", {}), **entry.get("mouth", {})}
            le    = {**default.get("left_eye",  {}), **entry.get("left_eye",  {})}
            re    = {**default.get("right_eye", {}), **entry.get("right_eye", {})}
        else:
            mouth = default.get("mouth", {})
            le    = default.get("left_eye", {})
            re    = default.get("right_eye", {})
        return _from_dict(image_size, mouth, le, re, outline)

    return _from_dict(
        image_size,
        data["mouth"], data["left_eye"], data["right_eye"],
        data.get("outline_color", [26, 26, 46, 255]),
    )


def _color_distance_sq(
    px: tuple[int, int, int, int],
    other: tuple[int, int, int, int],
) -> int:
    return sum((int(px[i]) - int(other[i])) ** 2 for i in range(3))


def _sample_skin_color(img: Image.Image, a: FaceAnchors) -> tuple[int, int, int, int]:
    """Sample nearby face pixels for the patch color.

    A single sample point is fragile: it can land on the nose or old mouth
    line, which paints a dark patch and creates the "double mouth" look.
    This samples several cheek/upper-lip areas and rejects outline-colored
    pixels before taking a median.
    """
    w, h = img.size
    offsets = (
        (0.0, -2.8),
        (-1.6, -1.2),
        (1.6, -1.2),
        (-1.9, 0.0),
        (1.9, 0.0),
        (-1.2, 1.2),
        (1.2, 1.2),
    )
    samples: list[tuple[int, int, int, int]] = []
    radius = 3
    min_outline_distance = 70 * 70
    for x_mult, y_mult in offsets:
        cx = int(a.mouth_cx + a.mouth_open_w * x_mult)
        cy = int(a.mouth_cy + a.mouth_open_h * y_mult)
        for yy in range(cy - radius, cy + radius + 1):
            for xx in range(cx - radius, cx + radius + 1):
                xx = max(0, min(w - 1, xx))
                yy = max(0, min(h - 1, yy))
                raw = img.getpixel((xx, yy))
                if not isinstance(raw, tuple) or len(raw) < 3:
                    continue
                alpha = int(raw[3]) if len(raw) >= 4 else 255
                if alpha <= 200:
                    continue
                px = (int(raw[0]), int(raw[1]), int(raw[2]), 255)
                if _color_distance_sq(px, a.outline_color) <= min_outline_distance:
                    continue
                samples.append(px)

    if samples:
        channels = [
            sorted(px[i] for px in samples)[len(samples) // 2]
            for i in range(3)
        ]
        return (channels[0], channels[1], channels[2], 255)

    return (244, 220, 195, 255)


def _patch_mouth(draw: ImageDraw.ImageDraw, a: FaceAnchors,
                 skin: tuple[int, int, int, int],
                 scale: int = 1) -> None:
    if a.mouth_box:
        x, y, w, h = a.mouth_box
        bbox = (x, y, x + w, y + h)
    else:
        w = a.mouth_open_w + MOUTH_PATCH_PAD_W * scale
        h = a.mouth_open_h + MOUTH_PATCH_PAD_H * scale
        bbox = (
            a.mouth_cx - w // 2, a.mouth_cy - h // 2,
            a.mouth_cx + w // 2, a.mouth_cy + h // 2,
        )
    if hasattr(draw, "rounded_rectangle"):
        draw.rounded_rectangle(bbox, radius=max(2, h // 3), fill=skin)
    else:
        draw.rectangle(bbox, fill=skin)


def _cubic_points(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    n: int = 36,
) -> list[tuple[int, int]]:
    pts: list[tuple[int, int]] = []
    for i in range(n + 1):
        t = i / n
        mt = 1.0 - t
        x = (
            mt ** 3 * p0[0]
            + 3 * mt ** 2 * t * p1[0]
            + 3 * mt * t ** 2 * p2[0]
            + t ** 3 * p3[0]
        )
        y = (
            mt ** 3 * p0[1]
            + 3 * mt ** 2 * t * p1[1]
            + 3 * mt * t ** 2 * p2[1]
            + t ** 3 * p3[1]
        )
        pts.append((round(x), round(y)))
    return pts


def _face_roll_radians(a: FaceAnchors) -> float:
    """Estimate head tilt from the eye line.

    The mouth anchor gives position/size; the eye anchors give roll. This keeps
    tilted-head poses from getting a perfectly horizontal mouth stamped on.
    """
    dx = a.right_eye_cx - a.left_eye_cx
    dy = a.right_eye_cy - a.left_eye_cy
    if abs(dx) < 1:
        return 0.0
    angle = math.atan2(dy, dx)
    if abs(angle) < math.radians(0.5):
        return 0.0
    return angle


def _rotate_points(
    pts: list[tuple[int, int]],
    cx: int,
    cy: int,
    angle: float,
) -> list[tuple[int, int]]:
    if abs(angle) < 1e-4:
        return pts
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    out: list[tuple[int, int]] = []
    for x, y in pts:
        dx = x - cx
        dy = y - cy
        out.append((
            round(cx + dx * cos_a - dy * sin_a),
            round(cy + dx * sin_a + dy * cos_a),
        ))
    return out


def _rotated_ellipse_points(
    cx: int,
    cy: int,
    w: int,
    h: int,
    angle: float,
    n: int = 48,
) -> list[tuple[int, int]]:
    pts: list[tuple[int, int]] = []
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    rx = w / 2
    ry = h / 2
    for i in range(n):
        theta = (math.tau * i) / n
        dx = math.cos(theta) * rx
        dy = math.sin(theta) * ry
        pts.append((
            round(cx + dx * cos_a - dy * sin_a),
            round(cy + dx * sin_a + dy * cos_a),
        ))
    return pts


def _smile_points(cx: int, cy: int, w: int, h: int) -> list[tuple[int, int]]:
    """Closed mouth: one smile stroke, not a flat dash."""
    left = (cx - w / 2, cy - h * 0.10)
    right = (cx + w / 2, cy - h * 0.10)
    return _cubic_points(
        left,
        (cx - w * 0.25, cy + h * 0.45),
        (cx + w * 0.25, cy + h * 0.45),
        right,
        n=40,
    )


def _crescent_polygon(cx: int, cy: int, w: int, h: int) -> list[tuple[int, int]]:
    """Open mouth: flat-ish upper edge plus rounded lower edge.

    The top is not a pointed diamond corner-to-corner line; the lower curve
    carries most of the opening. Reads as a soft cartoon mouth.
    """
    left = (cx - w / 2, cy - h * 0.28)
    right = (cx + w / 2, cy - h * 0.28)
    top = _cubic_points(
        left,
        (cx - w * 0.22, cy - h * 0.20),
        (cx + w * 0.22, cy - h * 0.20),
        right,
        n=32,
    )
    bottom = _cubic_points(
        right,
        (cx + w * 0.32, cy + h * 0.92),
        (cx - w * 0.32, cy + h * 0.92),
        left,
        n=40,
    )
    return top + bottom


def _draw_open_mouth(
    draw: ImageDraw.ImageDraw,
    a: FaceAnchors,
    kind: str,
    cx: int,
    cy: int,
    w: int,
    h: int,
    angle: float,
) -> None:
    """Draw a stylized open mouth — crescent or oval."""
    outline = a.outline_color

    if kind == "round":
        draw.polygon(_rotated_ellipse_points(cx, cy, w, h, angle), fill=outline)
        return

    draw.polygon(_rotate_points(_crescent_polygon(cx, cy, w, h), cx, cy, angle), fill=outline)


def _draw_mouth_shape(draw: ImageDraw.ImageDraw, a: FaceAnchors, shape: str) -> None:
    """Draw one of MOUTH_SHAPES on top of an already-skin-patched face area."""
    if shape not in MOUTH_SHAPES:
        raise ValueError(f"unknown mouth shape {shape!r}; valid: {list(MOUTH_SHAPES)}")
    spec = MOUTH_SHAPES[shape]
    w = max(3, int(a.mouth_open_w * spec["w_mult"]))
    h = max(3, int(a.mouth_open_h * spec["h_mult"]))
    scale = _anchor_scale(a)
    cx = a.mouth_cx + round(float(spec.get("x_offset", 0)) * scale)
    cy = a.mouth_cy + round(float(spec.get("y_offset", 0)) * scale)
    angle = _face_roll_radians(a)
    if spec["kind"] == "smile":
        draw.line(
            _rotate_points(_smile_points(cx, cy, w, h), cx, cy, angle),
            fill=a.outline_color,
            width=max(1, round(3 * scale)),
            joint="curve",
        )
        return

    _draw_open_mouth(
        draw=draw,
        a=a,
        kind=str(spec["kind"]),
        cx=cx,
        cy=cy,
        w=w,
        h=h,
        angle=angle,
    )


def _draw_eyes_closed_after_patch(draw: ImageDraw.ImageDraw, a: FaceAnchors) -> None:
    """Eyes closed = short horizontal line — Hanna-Barbera blink shape."""
    angle = _face_roll_radians(a)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    for cx, cy, w in (
        (a.left_eye_cx,  a.left_eye_cy,  a.left_eye_w),
        (a.right_eye_cx, a.right_eye_cy, a.right_eye_w),
    ):
        half_w = w / 2
        p0 = (
            round(cx - half_w * cos_a),
            round(cy - half_w * sin_a),
        )
        p1 = (
            round(cx + half_w * cos_a),
            round(cy + half_w * sin_a),
        )
        draw.line(
            [p0, p1],
            fill=a.outline_color, width=max(1, round(3 * _anchor_scale(a))),
        )


def _anchor_scale(a: FaceAnchors) -> float:
    return max(1.0, a.image_size[0] / 1024)


def _scaled_anchors(a: FaceAnchors, scale: int) -> FaceAnchors:
    return FaceAnchors(
        image_size=(a.image_size[0] * scale, a.image_size[1] * scale),
        mouth_cx=a.mouth_cx * scale,
        mouth_cy=a.mouth_cy * scale,
        mouth_open_w=a.mouth_open_w * scale,
        mouth_open_h=a.mouth_open_h * scale,
        mouth_box=(
            a.mouth_box[0] * scale,
            a.mouth_box[1] * scale,
            a.mouth_box[2] * scale,
            a.mouth_box[3] * scale,
        ) if a.mouth_box else None,
        left_eye_cx=a.left_eye_cx * scale,
        left_eye_cy=a.left_eye_cy * scale,
        left_eye_w=a.left_eye_w * scale,
        left_eye_h=a.left_eye_h * scale,
        right_eye_cx=a.right_eye_cx * scale,
        right_eye_cy=a.right_eye_cy * scale,
        right_eye_w=a.right_eye_w * scale,
        right_eye_h=a.right_eye_h * scale,
        outline_color=a.outline_color,
    )


def _draw_face_overlay(
    base_size: tuple[int, int],
    anchors: FaceAnchors,
    mouth: str,
    eyes: str,
    skin: tuple[int, int, int, int],
) -> Image.Image:
    scaled_size = (
        base_size[0] * OVERLAY_AA_SCALE,
        base_size[1] * OVERLAY_AA_SCALE,
    )
    scaled_anchors = _scaled_anchors(anchors, OVERLAY_AA_SCALE)
    overlay = Image.new("RGBA", scaled_size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    _patch_mouth(draw, scaled_anchors, skin, scale=OVERLAY_AA_SCALE)
    _draw_mouth_shape(draw, scaled_anchors, mouth)
    if eyes == "closed":
        _draw_eyes_closed_after_patch(draw, scaled_anchors)
    return overlay.resize(base_size, Image.Resampling.LANCZOS)


def render_face_state(
    base_png: str | Path,
    anchors: FaceAnchors,
    mouth: str,            # one of MOUTH_SHAPES — "closed" | "small" | "wide" | "round"
    eyes: str,             # "open" | "closed"
    output_path: str | Path,
) -> Path:
    """Render base.png with the requested mouth+eye state → output_path.

    Mouth handling — the source's drawn mouth is erased via a skin-color patch,
    then replaced with a mouth shape. Eyes:
      - "open"   = base.png unchanged (original eye dots read correctly)
      - "closed" = overlay a thin horizontal line on top to read as a blink
    """
    base = Image.open(base_png).convert("RGBA")
    skin = _sample_skin_color(base, anchors)
    overlay = _draw_face_overlay(
        base_size=base.size,
        anchors=anchors,
        mouth=mouth,
        eyes=eyes,
        skin=skin,
    )
    base.alpha_composite(overlay)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    base.save(output_path, "PNG")
    return output_path
