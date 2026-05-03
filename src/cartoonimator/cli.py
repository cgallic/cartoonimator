"""Command-line entry point."""
from __future__ import annotations

import argparse
import sys

from .mascot import render_scene
from .tagger import serve


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

    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
