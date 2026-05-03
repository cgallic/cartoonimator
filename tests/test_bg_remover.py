"""Chroma-key background removal tests."""
from __future__ import annotations

from PIL import Image

from cartoonimator.bg_remover import green_alpha, is_green_bg, remove_green


def test_pure_green_detected():
    assert is_green_bg(0, 255, 0) is True


def test_olive_green_detected():
    assert is_green_bg(140, 176, 85) is True


def test_warm_skin_not_detected():
    assert is_green_bg(220, 180, 150) is False


def test_blue_shirt_not_detected():
    assert is_green_bg(92, 140, 255) is False


def test_pure_green_alpha_zero():
    assert green_alpha(0, 255, 0) == 0


def test_skin_alpha_full():
    assert green_alpha(220, 180, 150) == 255


def test_remove_green_writes_transparent_png(tmp_path):
    src = Image.new("RGB", (10, 10), (0, 255, 0))
    for y in range(3, 7):
        for x in range(3, 7):
            src.putpixel((x, y), (200, 30, 30))
    in_path = tmp_path / "in.png"
    src.save(in_path)
    out_path = tmp_path / "out.png"
    remove_green(in_path, out_path)
    out = Image.open(out_path).convert("RGBA")
    center = out.getpixel((5, 5))
    corner = out.getpixel((0, 0))
    assert isinstance(center, tuple) and center[3] == 255
    assert isinstance(corner, tuple) and corner[3] == 0
