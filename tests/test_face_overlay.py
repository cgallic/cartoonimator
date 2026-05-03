"""Face anchor loading tests — covers v1 + v2 schemas."""
from __future__ import annotations

import json

from cartoonimator.face_overlay import load_anchors


def _v1_anchors() -> dict:
    return {
        "image_size": [1024, 1024],
        "mouth": {"cx": 512, "cy": 600, "open_w": 30, "open_h": 18},
        "left_eye": {"cx": 480, "cy": 540, "w": 18, "h": 12},
        "right_eye": {"cx": 544, "cy": 540, "w": 18, "h": 12},
        "outline_color": [26, 26, 46, 255],
    }


def _v2_anchors() -> dict:
    return {
        "image_size": [1024, 1024],
        "default": {
            "mouth": {"cx": 512, "cy": 600, "open_w": 30, "open_h": 18},
            "left_eye": {"cx": 480, "cy": 540, "w": 18, "h": 12},
            "right_eye": {"cx": 544, "cy": 540, "w": 18, "h": 12},
            "outline_color": [26, 26, 46, 255],
        },
        "per_pose": {
            "tilted_pose": {
                "mouth": {"cx": 500, "cy": 620},
                "left_eye": {"cx": 470, "cy": 555},
                "right_eye": {"cx": 535, "cy": 545},
            },
        },
    }


def test_load_v1(tmp_path):
    p = tmp_path / "anchors.json"
    p.write_text(json.dumps(_v1_anchors()))
    a = load_anchors(p)
    assert a.mouth_cx == 512
    assert a.left_eye_cx == 480


def test_load_v2_default(tmp_path):
    p = tmp_path / "anchors.json"
    p.write_text(json.dumps(_v2_anchors()))
    a = load_anchors(p)
    assert a.mouth_cx == 512


def test_load_v2_per_pose_overrides(tmp_path):
    p = tmp_path / "anchors.json"
    p.write_text(json.dumps(_v2_anchors()))
    a = load_anchors(p, pose_id="tilted_pose")
    assert a.mouth_cx == 500
    assert a.mouth_cy == 620
    # mouth_open_w not overridden — inherited from default
    assert a.mouth_open_w == 30
    # left eye y differs from right eye y → roll computed correctly
    assert a.left_eye_cy != a.right_eye_cy


def test_load_v2_unknown_pose_falls_back_to_default(tmp_path):
    p = tmp_path / "anchors.json"
    p.write_text(json.dumps(_v2_anchors()))
    a = load_anchors(p, pose_id="not-a-real-pose")
    assert a.mouth_cx == 512  # default
