"""Library-generation tests that don't need network or an API key."""
from __future__ import annotations

import json

from cartoonimator.library import (
    extract_base_prompt,
    write_background_manifest,
    write_pose_manifest,
)


def test_extract_base_prompt_picks_first_fence():
    bible = """
# Some character

Some text.

```
First fenced block.
With multiple lines.
```

Other text.

```
Second block — should not be picked.
```
"""
    out = extract_base_prompt(bible)
    assert "First fenced block" in out
    assert "Second block" not in out


def test_extract_base_prompt_no_fence_returns_empty():
    assert extract_base_prompt("# Just a heading\n\nNo code blocks here.") == ""


def test_write_pose_manifest(tmp_path):
    poses = [
        {"id": "a", "filename": "a.png", "description": "first",
         "env_tags": ["any"], "props": []},
        {"id": "b", "filename": "b.png", "description": "second",
         "env_tags": ["any"], "props": []},
    ]
    path = write_pose_manifest(tmp_path, "test_char", poses)
    assert path == tmp_path / "poses-manifest.json"
    data = json.loads(path.read_text())
    assert data["character"] == "test_char"
    assert len(data["poses"]) == 2
    assert data["poses"][0]["id"] == "a"


def test_write_background_manifest(tmp_path):
    bgs = [
        {"id": "navy", "filename": "navy.png", "description": "deep navy",
         "env_tags": ["abstract"]},
    ]
    path = write_background_manifest(tmp_path, bgs)
    assert path == tmp_path / "manifest.json"
    data = json.loads(path.read_text())
    assert data["backgrounds"][0]["id"] == "navy"
