"""Chroma-key background removal — green-screen → transparent PNG.

Detects #00FF00 + olive + yellow-green variants and writes a transparent PNG
with anti-aliased edges. Useful when AI-generating poses against a green
background, then keying out the background to layer on real scenes.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image


def is_green_bg(r: int, g: int, b: int) -> bool:
    """Detect all green background variants: bright #00FF00, olive, muted, yellow-green."""
    if g > 150 and g > r * 1.4 and g > b * 1.4:
        return True
    if g > 100 and g > r and g > b and r < 200 and b < 150:
        if g - max(r, b) > 15:
            return True
    if g > 130 and 80 < r < g and b < g * 0.7:
        if g - r > 10 and b < 120:
            return True
    return False


def green_alpha(r: int, g: int, b: int) -> int:
    """Return alpha 0 (fully transparent) for green pixels, partial for edges, 255 otherwise."""
    if is_green_bg(r, g, b):
        return 0
    green_dominance = g - max(r, b)
    if green_dominance > 5 and g > 80 and b < 150:
        return max(0, min(255, 255 - int(green_dominance * 8)))
    return 255


def remove_green(src_path: str | Path, out_path: str | Path) -> Path:
    """Read PNG/JPG with green background; write transparent PNG to out_path."""
    src_path = Path(src_path)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    img = Image.open(src_path).convert("RGBA")
    pixels = img.load()
    if pixels is None:
        raise RuntimeError(f"could not load pixel data from {src_path}")
    w, h = img.size
    for y in range(h):
        for x in range(w):
            px = pixels[x, y]
            assert isinstance(px, tuple) and len(px) == 4
            r, g, b, _ = px
            new_alpha = green_alpha(r, g, b)
            if new_alpha == 0:
                pixels[x, y] = (0, 0, 0, 0)
            elif new_alpha < 255:
                pixels[x, y] = (r, g, b, new_alpha)
    img.save(out_path, "PNG")
    return out_path
