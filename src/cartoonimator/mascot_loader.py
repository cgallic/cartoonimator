"""Load a mascot directory into a structured object."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Mascot:
    """A mascot is a directory with poses, anchors, and a manifest."""

    root: Path
    name: str
    pose_ids: list[str]
    pose_files: dict[str, Path]
    anchors_path: Path
    bible_text: str = ""
    poses_with_per_pose_anchors: set[str] = field(default_factory=set)

    def has_per_pose_anchor(self, pose_id: str) -> bool:
        return pose_id in self.poses_with_per_pose_anchors

    def pose_path(self, pose_id: str) -> Path:
        if pose_id not in self.pose_files:
            raise KeyError(
                f"pose {pose_id!r} not in mascot {self.name!r}; "
                f"known poses: {sorted(self.pose_files)[:5]}…"
            )
        return self.pose_files[pose_id]


def load_mascot(root: str | Path) -> Mascot:
    """Load mascot at `root`, returning a Mascot record.

    Required layout:
        root/
          ├── poses-manifest.json   # {"character": "name", "poses": [{id, filename, ...}]}
          ├── anchors.json          # v2 schema with default + per_pose
          ├── poses/                # PNG files referenced by manifest
          └── character-bible.md    # optional personality notes
    """
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(f"mascot directory not found: {root}")

    manifest_path = root / "poses-manifest.json"
    anchors_path = root / "anchors.json"
    poses_dir = root / "poses"

    if not manifest_path.is_file():
        raise FileNotFoundError(f"missing {manifest_path}")
    if not anchors_path.is_file():
        raise FileNotFoundError(f"missing {anchors_path}")
    if not poses_dir.is_dir():
        raise FileNotFoundError(f"missing {poses_dir}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    anchors = json.loads(anchors_path.read_text(encoding="utf-8"))

    pose_ids: list[str] = []
    pose_files: dict[str, Path] = {}
    for entry in manifest.get("poses", []):
        pid = entry["id"]
        fname = entry["filename"]
        pose_path = poses_dir / fname
        pose_ids.append(pid)
        pose_files[pid] = pose_path

    bible_path = root / "character-bible.md"
    bible_text = bible_path.read_text(encoding="utf-8") if bible_path.is_file() else ""

    per_pose = anchors.get("per_pose", {}) if isinstance(anchors, dict) else {}

    return Mascot(
        root=root,
        name=manifest.get("character", root.name),
        pose_ids=pose_ids,
        pose_files=pose_files,
        anchors_path=anchors_path,
        bible_text=bible_text,
        poses_with_per_pose_anchors=set(per_pose.keys()),
    )
