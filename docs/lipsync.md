# Lipsync

Audio → mouth shapes via Rhubarb Lip Sync.

## Install Rhubarb

Download the binary from https://github.com/DanielSWolf/rhubarb-lip-sync/releases and put it on `$PATH`. Or set `RHUBARB_BINARY=/path/to/rhubarb`.

## How it works

Rhubarb maps a WAV → 9 Preston-Blair phonemes (A, B, C, D, E, F, G, H, X). For a stylized cartoon at 30 fps, 9 shapes is too many — you get flicker and the eye can't read the difference. We collapse to 4:

```
X, A     → closed (silence, M/B/P consonants)
B, F, G  → small  (K/S/T/N/D + V/F lip-tuck)
C, D, H  → wide   (AE/EH/AA + L)
E        → round  (AO/UR/UW — "oh"/"oo")
```

Then `smooth_timeline` drops anything shorter than 70 ms (~2 frames at 30 fps), absorbing micro-flickers into adjacent shapes.

## Tuning

```python
from cartoonimator import (
    viseme_track,
    collapse_to_4_shapes,
    smooth_timeline,
)

cues = viseme_track("audio.wav", transcript="Hello world.")
segments_4 = collapse_to_4_shapes(cues)
smoothed = smooth_timeline(segments_4, min_hold_s=0.085)  # tighter
```

`min_hold_s` is the only knob most users need:

- **0.050** (50ms) — preserves more Rhubarb detail, may flicker on fast speech
- **0.070** (default) — good balance
- **0.100** (100ms) — calmer mouth, may miss quick consonant pairs

## Transcripts improve accuracy

Rhubarb uses PocketSphinx for phoneme alignment. If you pass the spoken text, alignment is noticeably more accurate, especially for rare words and proper nouns:

```python
viseme_track("hello.wav", transcript="Hi I'm Kai. AI illustrates, code animates.")
```

In `render_scene`, pass `transcript=` to forward this to Rhubarb.

## What about 9 shapes?

We render 4. The remaining 5 visemes (B/F/G/C/D/H) collapse into `small` and `wide`. If your art style genuinely benefits from a separate F/V shape (lip-tuck), it's a 1-shape addition before going to full 9 — not the other way around.

## When Rhubarb fails

If Rhubarb isn't available or the audio is too noisy for alignment, the renderer falls back to a fixed flap pattern (closed → small → wide → small) at ~7.7 Hz. The mouth still moves with the audio's *envelope*, just not the phoneme content. Better than no animation; worse than real lipsync.

## Audio formats

Rhubarb wants WAV. The renderer transparently converts whatever you give it to mono 16 kHz WAV via FFmpeg before invoking Rhubarb. So MP3, OGG, M4A all work as input — just expect slight quality loss vs. starting from a raw WAV.
