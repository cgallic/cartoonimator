# Architecture

> **AI illustrates, code animates.**

## The split

Diffusion models are great at illustrating consistent character art at a single moment in time. They are **bad at frame-to-frame consistency** — every frame redraws the body. Hands grow extra fingers between frames. Eyebrows jiggle. Costume seams shift. The face wobbles imperceptibly but enough to break the cartoon illusion.

So we split the job:

| Layer            | Tool                          | Runs       |
|------------------|-------------------------------|------------|
| Body illustration | Stable Diffusion / GPT Image / Midjourney | Once per pose, ahead of time |
| Mouth/eye states  | PIL drawing primitives        | Every render |
| Audio → visemes   | Rhubarb Lip Sync              | Every render |
| Frame compositing | PIL `alpha_composite`         | Every render |
| Encode + mux      | FFmpeg                        | Every render |

The body PNG is **immutable** at render time. The renderer never asks an AI model to redraw the character. It draws a small mouth shape on top at known anchor coordinates. That's it.

## The render pipeline

```
audio.wav  ─┐
            ├──► Rhubarb ──► visemes (A,B,C,D,E,F,G,H,X)
            │                 │
            │                 ▼
            │       collapse_to_4_shapes
            │                 │
            │                 ▼
            │       smooth_timeline (drop <70ms flickers)
            │                 │
            │                 ▼
            │       mouth timeline: [(t0,t1,closed), (t1,t2,wide), ...]
            │
mascot/    ─┤
            │
            ▼
   ┌─────────────────────────────────────────┐
   │  pre-render mouth states on each pose   │
   │  (closed/small/wide/round + blink)      │
   │  using face_overlay + per-pose anchors  │
   └─────────────────────────────────────────┘
                    │
                    ▼
            cut_picker: every 2s, switch to next pose
                    │
                    ▼
            build Shot list = (pose+mouth PNG, bg, duration)
                    │
                    ▼
            insert blink halfway if scene ≥ 3s
                    │
                    ▼
   ┌─────────────────────────────────────────┐
   │  ffmpeg: composite each shot,           │
   │          loop-encode for shot.duration, │
   │          concat-demux,                  │
   │          mux audio (voice + music)      │
   └─────────────────────────────────────────┘
                    │
                    ▼
              output.mp4
```

## Why anchors per pose

A flat anchor (one mouth coordinate for the whole character) only works if every pose has the head in the same orientation at the same place. Real character art doesn't.

Per-pose anchors let the renderer:

1. Patch out the *original* drawn mouth in this pose's specific face box, with skin-color sampled from this pose's cheeks
2. Draw the new mouth at the correct screen coordinates for this pose
3. Compute head roll from the eye line, so a tilted head doesn't get a horizontal mouth stamped on

This is why `cartoonimator tag` exists — to record those coordinates by clicking on each pose once, ever.

## The eye-line roll trick

Head tilt is computed from the eye line, not declared:

```python
angle = atan2(right_eye.cy - left_eye.cy, right_eye.cx - left_eye.cx)
```

If the right eye is lower than the left, the head is tilted right. Mouth polygons and blink lines are rotated by this angle. No facial landmark detection, no mesh, no rigging — just two eye coordinates per pose.

## The 9-to-4 viseme collapse

Rhubarb gives you 9 Preston-Blair phonemes (A, B, C, D, E, F, G, H, X). Animating 9 distinct mouth shapes is overkill for a stylized cartoon — you get more wobble than expression for each new shape you add.

The renderer collapses to 4:

| Group           | Visemes | Mouth state |
|-----------------|---------|-------------|
| silence / closed | X, A   | smile stroke |
| narrow open     | B, F, G | small crescent |
| wide open       | C, D, H | wide crescent  |
| rounded         | E       | oval O |

Tested baseline: this reads cleanly on a 1080×1920 cartoon at 30fps. Going to 9 shapes is reserved for cases where 4 truly fails (none observed yet).

## What this design rules out

- **Frame interpolation between poses.** Cuts are hard cuts. There's no in-betweening.
- **Real-time rendering.** Pre-rendering 4 mouths × N poses takes a few seconds; the bottleneck is FFmpeg encode.
- **Photorealism.** The body is static between frames — that immediately reads "cartoon," not "video."
- **Camera moves.** The frame is fixed at 1080×1920. No pans, zooms, or perspective.

These are deliberate. The whole point is that the body doesn't move between frames.
