"""Library generation — turn pose specs into a complete mascot directory.

This is a one-time setup tool, not part of the daily render path. It uses
GPT Image 2 (via OpenRouter) to render each pose against a green screen,
then keys the green out to produce transparent PNGs ready to be tagged.

Workflow:
  1. Write a `character-bible.md` whose first ```...``` block is the base
     prompt (style + identity that should ride along on every pose).
  2. Write `pose-specs.json` — a list of `{id, prompt, description, env_tags, props}`.
  3. Run `cartoonimator build-library --char-dir mascots/myname` (requires
     `OPENROUTER_API_KEY` in env).
  4. Run `cartoonimator tag --mascot mascots/myname` to anchor mouth/eye points.
  5. `cartoonimator render ...`.
"""
from .build import (
    build_background_library,
    build_character_library,
    extract_base_prompt,
    write_background_manifest,
    write_pose_manifest,
)

__all__ = [
    "build_character_library",
    "build_background_library",
    "extract_base_prompt",
    "write_pose_manifest",
    "write_background_manifest",
]
