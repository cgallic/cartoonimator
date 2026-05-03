"""Library generation — pose specs + character bible → transparent PNG library."""
from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from ..bg_remover import remove_green
from ._gpt_image import GPTImageClient

MANIFEST_VERSION = "1.0.0"
DEFAULT_WORKERS = 5  # OpenRouter standard tier ~200 RPM; 5 concurrent is conservative


def _make_client(api_key: str | None = None) -> GPTImageClient:
    key = api_key or os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError(
            "OPENROUTER_API_KEY missing — set the env var or pass api_key"
        )
    return GPTImageClient(api_key=key)


def write_pose_manifest(char_dir: Path, character: str, poses: list[dict]) -> Path:
    char_dir.mkdir(parents=True, exist_ok=True)
    path = char_dir / "poses-manifest.json"
    path.write_text(
        json.dumps(
            {"character": character, "version": MANIFEST_VERSION, "poses": poses},
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def write_background_manifest(bg_dir: Path, backgrounds: list[dict]) -> Path:
    bg_dir.mkdir(parents=True, exist_ok=True)
    path = bg_dir / "manifest.json"
    path.write_text(
        json.dumps(
            {"version": MANIFEST_VERSION, "backgrounds": backgrounds},
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def extract_base_prompt(bible_text: str) -> str:
    """Pull the first triple-backtick block out of a character bible."""
    in_fence = False
    lines: list[str] = []
    for line in bible_text.splitlines():
        if line.strip().startswith("```"):
            if in_fence:
                return "\n".join(lines).strip()
            in_fence = True
            continue
        if in_fence:
            lines.append(line)
    return "\n".join(lines).strip()


def build_character_library(
    character: str,
    char_dir: str | Path,
    pose_specs: list[dict],
    base_prompt: str,
    anchor_image_path: str | Path | None = None,
    api_key: str | None = None,
    workers: int = DEFAULT_WORKERS,
) -> dict:
    """Generate every pose in `pose_specs` for one character.

    Each `pose_spec` must have: `id`, `prompt`, `description`. Optional:
    `env_tags`, `props`. Output: `<char_dir>/raw/<id>.png` (with green bg)
    plus `<char_dir>/poses/<id>.png` (transparent, post-keying).

    Generation is concurrent (`workers`); already-generated poses are skipped.

    Args:
        character: name (used in manifest)
        char_dir: directory to write into (created if missing)
        pose_specs: list of pose-spec dicts
        base_prompt: character description prepended to every pose prompt
        anchor_image_path: optional reference image for style consistency
            (passed to GPT Image 2). Falls back to the first generated raw
            PNG on later runs.
        api_key: OpenRouter API key (overrides OPENROUTER_API_KEY env)
        workers: concurrent generations
    """
    char_dir = Path(char_dir)
    client = _make_client(api_key)
    raw_dir = char_dir / "raw"
    poses_dir = char_dir / "poses"
    raw_dir.mkdir(parents=True, exist_ok=True)
    poses_dir.mkdir(parents=True, exist_ok=True)

    anchor_bytes: bytes | None = None
    if anchor_image_path and Path(anchor_image_path).exists():
        anchor_bytes = Path(anchor_image_path).read_bytes()

    def _process_pose(spec: dict) -> tuple[dict, str, str | None]:
        raw_path = raw_dir / f"{spec['id']}.png"
        out_path = poses_dir / f"{spec['id']}.png"
        if out_path.exists() and raw_path.exists():
            return (spec, "skipped", None)
        full_prompt = f"{base_prompt}\n\nPose: {spec['prompt']}"
        try:
            images = client.generate(prompt=full_prompt, n=1, anchor_image=anchor_bytes)
            png = images[0].png_bytes
            raw_path.write_bytes(png)
            remove_green(raw_path, out_path)
            return (spec, "ok", None)
        except Exception as e:
            return (spec, "fail", repr(e))

    failed: list[str] = []
    succeeded_ids: set[str] = set()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_process_pose, s): s for s in pose_specs}
        for fut in as_completed(futs):
            spec, status, err = fut.result()
            if status == "skipped":
                print(f"[skip] {character}/{spec['id']} (already generated)")
                succeeded_ids.add(spec["id"])
            elif status == "ok":
                print(f"[ok]   {character}/{spec['id']}")
                succeeded_ids.add(spec["id"])
            else:
                print(f"[fail] {character}/{spec['id']}: {err}", file=sys.stderr)
                failed.append(spec["id"])

    manifest_entries: list[dict] = []
    for spec in pose_specs:
        if spec["id"] not in succeeded_ids:
            continue
        manifest_entries.append({
            "id": spec["id"],
            "filename": f"{spec['id']}.png",
            "description": spec["description"],
            "env_tags": spec.get("env_tags", ["any"]),
            "props": spec.get("props", []),
        })

    write_pose_manifest(char_dir, character, manifest_entries)
    return {
        "character": character,
        "count": len(manifest_entries),
        "failed": failed,
        "char_dir": str(char_dir),
    }


def build_background_library(
    bg_dir: str | Path,
    bg_specs: list[dict],
    api_key: str | None = None,
    workers: int = DEFAULT_WORKERS,
) -> dict:
    """Generate background PNGs (no green-keying — these are full-frame backdrops)."""
    bg_dir = Path(bg_dir)
    client = _make_client(api_key)
    bg_dir.mkdir(parents=True, exist_ok=True)

    def _process_bg(spec: dict) -> tuple[dict, str, str | None]:
        out_path = bg_dir / f"{spec['id']}.png"
        if out_path.exists():
            return (spec, "skipped", None)
        try:
            images = client.generate(prompt=spec["prompt"], n=1)
            png = images[0].png_bytes
            out_path.write_bytes(png)
            return (spec, "ok", None)
        except Exception as e:
            return (spec, "fail", repr(e))

    failed: list[str] = []
    succeeded_ids: set[str] = set()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_process_bg, s): s for s in bg_specs}
        for fut in as_completed(futs):
            spec, status, err = fut.result()
            if status == "skipped":
                print(f"[skip] background/{spec['id']} (already generated)")
                succeeded_ids.add(spec["id"])
            elif status == "ok":
                print(f"[ok]   background/{spec['id']}")
                succeeded_ids.add(spec["id"])
            else:
                print(f"[fail] background/{spec['id']}: {err}", file=sys.stderr)
                failed.append(spec["id"])

    manifest_entries: list[dict] = []
    for spec in bg_specs:
        if spec["id"] not in succeeded_ids:
            continue
        manifest_entries.append({
            "id": spec["id"],
            "filename": f"{spec['id']}.png",
            "description": spec["description"],
            "env_tags": spec.get("env_tags", ["any"]),
        })
    write_background_manifest(bg_dir, manifest_entries)
    return {"count": len(manifest_entries), "failed": failed, "bg_dir": str(bg_dir)}
