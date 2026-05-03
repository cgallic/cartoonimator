"""Command-line entry point."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .mascot import render_scene
from .tagger import serve
from .video_utils import cut_window, mix_music


def _cmd_render(args: argparse.Namespace) -> int:
    out = render_scene(
        mascot=args.mascot,
        audio_wav=args.audio,
        background_png=args.background,
        output=args.output,
        pose_cut_interval_s=args.pose_cut_interval,
        music_track=args.music,
        scale=args.scale,
        anchor=args.anchor,
        fps=args.fps,
        insert_blink=not args.no_blink,
        transcript=args.transcript,
    )
    print(f"wrote {out}")
    return 0


def _cmd_tag(args: argparse.Namespace) -> int:
    serve(args.mascot, port=args.port, bind=args.bind)
    return 0


def _cmd_mix_music(args: argparse.Namespace) -> int:
    out = mix_music(args.video, args.music, args.output, volume=args.volume)
    print(f"wrote {out}")
    return 0


def _cmd_cut(args: argparse.Namespace) -> int:
    out = cut_window(args.input, args.start, args.end, args.output)
    print(f"wrote {out}")
    return 0


def _cmd_build_library(args: argparse.Namespace) -> int:
    from .library import (
        build_background_library,
        build_character_library,
        extract_base_prompt,
    )

    char_dir = Path(args.char_dir)
    if args.backgrounds:
        spec_path = Path(args.pose_specs) if args.pose_specs else char_dir / "pose-specs.json"
        if not spec_path.is_file():
            print(f"missing {spec_path}", file=sys.stderr)
            return 1
        bg_specs = json.loads(spec_path.read_text(encoding="utf-8"))
        if args.limit is not None:
            bg_specs = bg_specs[: args.limit]
        result = build_background_library(char_dir, bg_specs, workers=args.workers)
        print(json.dumps(result, indent=2))
        return 0

    spec_path = Path(args.pose_specs) if args.pose_specs else char_dir / "pose-specs.json"
    bible_path = Path(args.bible) if args.bible else char_dir / "character-bible.md"
    if not spec_path.is_file():
        print(f"missing {spec_path}", file=sys.stderr)
        return 1
    if not bible_path.is_file():
        print(f"missing {bible_path}", file=sys.stderr)
        return 1

    pose_specs = json.loads(spec_path.read_text(encoding="utf-8"))
    if args.limit is not None:
        pose_specs = pose_specs[: args.limit]

    base_prompt = extract_base_prompt(bible_path.read_text(encoding="utf-8"))
    if not base_prompt:
        print(
            f"warning: no triple-backtick block found in {bible_path}; "
            "base_prompt is empty",
            file=sys.stderr,
        )

    anchor: Path | None = None
    if args.anchor_image:
        anchor = Path(args.anchor_image)
        if not anchor.exists():
            print(f"warning: --anchor-image {anchor} missing", file=sys.stderr)
            anchor = None
    if anchor is None and pose_specs:
        candidate = char_dir / "raw" / f"{pose_specs[0]['id']}.png"
        if candidate.exists():
            anchor = candidate

    character = args.character or char_dir.name
    result = build_character_library(
        character=character,
        char_dir=char_dir,
        pose_specs=pose_specs,
        base_prompt=base_prompt,
        anchor_image_path=anchor,
        workers=args.workers,
    )
    print(json.dumps(result, indent=2))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cartoonimator", description="AI illustrates, code animates.")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render", help="render a mascot scene to MP4")
    r.add_argument("--mascot", required=True, help="path to mascot directory")
    r.add_argument("--audio", required=True, help="path to spoken WAV (or any audio ffmpeg can read)")
    r.add_argument("--background", required=True, help="path to 1080x1920 background PNG")
    r.add_argument("--output", required=True, help="path to output MP4")
    r.add_argument("--pose-cut-interval", type=float, default=2.0, help="seconds between pose cuts")
    r.add_argument("--music", default=None, help="optional background music track")
    r.add_argument("--scale", type=float, default=0.85, help="pose height as fraction of canvas")
    r.add_argument("--anchor", default="center-bottom",
                   choices=["center-bottom", "center", "left-bottom", "right-bottom"])
    r.add_argument("--fps", type=int, default=30)
    r.add_argument("--no-blink", action="store_true", help="disable mid-scene blink insert")
    r.add_argument("--transcript", default=None,
                   help="optional spoken text — improves Rhubarb alignment")
    r.set_defaults(func=_cmd_render)

    t = sub.add_parser("tag", help="run the anchor tagger HTTP server")
    t.add_argument("--mascot", required=True, help="path to mascot directory")
    t.add_argument("--port", type=int, default=8801)
    t.add_argument("--bind", default="0.0.0.0")
    t.set_defaults(func=_cmd_tag)

    m = sub.add_parser("mix-music", help="mix a music track under an existing MP4's audio")
    m.add_argument("--video", required=True, help="input MP4")
    m.add_argument("--music", required=True, help="music track (any ffmpeg-readable format)")
    m.add_argument("--output", required=True, help="output MP4")
    m.add_argument("--volume", type=float, default=0.15, help="music level 0–1 under voice")
    m.set_defaults(func=_cmd_mix_music)

    c = sub.add_parser("cut", help="extract a [start, end] window from a video")
    c.add_argument("--input", required=True, help="input video")
    c.add_argument("--start", type=float, required=True, help="start in seconds")
    c.add_argument("--end", type=float, required=True, help="end in seconds")
    c.add_argument("--output", required=True, help="output MP4")
    c.set_defaults(func=_cmd_cut)

    b = sub.add_parser(
        "build-library",
        help="generate a mascot's pose library from pose-specs.json + character-bible.md "
             "(requires OPENROUTER_API_KEY)",
    )
    b.add_argument("--char-dir", required=True,
                   help="output directory for the character (e.g. mascots/myname)")
    b.add_argument("--character", default=None,
                   help="character name in manifest (defaults to directory basename)")
    b.add_argument("--pose-specs", default=None,
                   help="path to pose-specs.json (defaults to <char-dir>/pose-specs.json)")
    b.add_argument("--bible", default=None,
                   help="path to character-bible.md (defaults to <char-dir>/character-bible.md)")
    b.add_argument("--anchor-image", default=None,
                   help="optional style-reference PNG (defaults to first existing raw output)")
    b.add_argument("--limit", type=int, default=None,
                   help="only build the first N specs (for sanity checks)")
    b.add_argument("--workers", type=int, default=5,
                   help="concurrent generations (default 5)")
    b.add_argument("--backgrounds", action="store_true",
                   help="treat --char-dir as a backgrounds directory and skip green-keying")
    b.set_defaults(func=_cmd_build_library)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
