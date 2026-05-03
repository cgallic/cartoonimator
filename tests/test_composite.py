"""Pose-on-background composite tests."""
from __future__ import annotations

import pytest
from PIL import Image

from cartoonimator.composite import composite_scene


def _bg(tmp_path):
    bg = Image.new("RGB", (1080, 1920), (50, 50, 50))
    p = tmp_path / "bg.png"
    bg.save(p)
    return p


def _pose(tmp_path):
    pose = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    for y in range(0, 1024):
        for x in range(212, 812):
            pose.putpixel((x, y), (255, 255, 255, 255))
    p = tmp_path / "pose.png"
    pose.save(p)
    return p


def test_output_dimensions(tmp_path):
    out = tmp_path / "out.png"
    composite_scene(_bg(tmp_path), _pose(tmp_path), output_path=out)
    img = Image.open(out)
    assert img.size == (1080, 1920)


def test_pose_visible_at_center_bottom(tmp_path):
    out = tmp_path / "out.png"
    composite_scene(_bg(tmp_path), _pose(tmp_path),
                    scale=0.85, anchor="center-bottom", output_path=out)
    img = Image.open(out).convert("RGB")
    px = img.getpixel((540, 1700))
    assert px == (255, 255, 255)


def test_anchor_center(tmp_path):
    out = tmp_path / "out.png"
    composite_scene(_bg(tmp_path), _pose(tmp_path),
                    scale=0.5, anchor="center", output_path=out)
    img = Image.open(out).convert("RGB")
    px = img.getpixel((540, 960))
    assert px == (255, 255, 255)


def test_returns_output_path(tmp_path):
    out = tmp_path / "out.png"
    result = composite_scene(_bg(tmp_path), _pose(tmp_path), output_path=out)
    assert result == out


def test_invalid_anchor_raises(tmp_path):
    with pytest.raises(ValueError):
        composite_scene(_bg(tmp_path), _pose(tmp_path), anchor="diagonal-zero")
