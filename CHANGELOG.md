# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `cartoonimator demo <output.mp4>` — render a sample MP4 from bundled Kai assets to verify a fresh install in one command.
- `py.typed` marker so downstream type-checkers (Pyright, mypy) trust the package's inline type annotations.
- README demo video embed.

## [0.1.0] — 2026-05-03

### Added

- Core engine: `composite`, `face_overlay`, `lipsync`, `scene`, `mascot`, `mascot_loader`.
- Anchor schema (v1 flat + v2 per-pose) with eye-line head-roll computation.
- Rhubarb 9-viseme → 4-state mouth collapse with 70 ms flicker smoothing.
- HTTP-based anchor tagger (`cartoonimator tag`) — click-to-anchor UI.
- TTS providers: `BYOProvider`, `ElevenLabsProvider`, `MossProvider`.
- `cartoonimator render` CLI for the mascot pipeline.
- `cartoonimator cut` and `cartoonimator mix-music` — generic FFmpeg helpers, also exposed as `cartoonimator.video_utils`.
- `cartoonimator build-library` (and `cartoonimator.library`) — generate green-screen poses with GPT Image 2 via OpenRouter, key out the green to produce transparent PNGs, and write `poses-manifest.json`.
- Reference mascot: Kai (41 poses, anchored).
- Examples: `hello_kai.py`, `beats_kaicalls.py`.
- Documentation: `architecture.md`, `anchors.md`, `lipsync.md`.
- CI for Python 3.11 and 3.12 on Ubuntu, with FFmpeg installed via apt.
- 34 passing tests, including an end-to-end render smoke test.
