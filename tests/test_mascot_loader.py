"""Mascot loader tests — uses the bundled Kai mascot directory."""
from __future__ import annotations

from pathlib import Path

import pytest

from cartoonimator import load_mascot
from cartoonimator.mascot_loader import Mascot

REPO_ROOT = Path(__file__).resolve().parents[1]
KAI_DIR = REPO_ROOT / "mascots" / "kai"


@pytest.mark.skipif(not KAI_DIR.is_dir(), reason="Kai mascot dir not present")
def test_load_kai():
    mascot = load_mascot(KAI_DIR)
    assert isinstance(mascot, Mascot)
    assert mascot.name == "kai"
    assert len(mascot.pose_ids) > 0
    # standard Kai pose should be present
    assert "standing_open_hands" in mascot.pose_files


@pytest.mark.skipif(not KAI_DIR.is_dir(), reason="Kai mascot dir not present")
def test_kai_has_per_pose_anchors():
    mascot = load_mascot(KAI_DIR)
    # Kai ships with per-pose anchors for all listed poses
    assert len(mascot.poses_with_per_pose_anchors) > 0


def test_missing_directory_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_mascot(tmp_path / "does-not-exist")


def test_missing_manifest_raises(tmp_path):
    bad = tmp_path / "broken"
    bad.mkdir()
    (bad / "anchors.json").write_text("{}")
    (bad / "poses").mkdir()
    with pytest.raises(FileNotFoundError):
        load_mascot(bad)
