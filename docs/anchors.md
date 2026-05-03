# Anchor schema

Each mascot ships with an `anchors.json` describing where the mouth and eyes are on each pose. The renderer reads this to know:

- Where to erase the original drawn mouth
- Where to draw the new mouth
- Where the eyes are (for blink rendering and head-roll computation)

## Schema

```json
{
  "image_size": [1024, 1024],
  "default": {
    "mouth": {
      "cx": 516, "cy": 150,
      "open_w": 36, "open_h": 18,
      "box": { "x": 501, "y": 144, "w": 31, "h": 14 }
    },
    "left_eye":  { "cx": 495, "cy": 107, "w": 18, "h": 12 },
    "right_eye": { "cx": 537, "cy": 107, "w": 18, "h": 12 },
    "outline_color": [26, 26, 46, 255]
  },
  "per_pose": {
    "thinking_hand_chin": {
      "mouth": {
        "cx": 502, "cy": 174,
        "box": { "x": 488, "y": 168, "w": 38, "h": 18 }
      },
      "left_eye":  { "cx": 483, "cy": 134, "w": 18, "h": 12 },
      "right_eye": { "cx": 519, "cy": 130, "w": 18, "h": 12 }
    }
  }
}
```

Each pose under `per_pose` inherits unspecified fields from `default`.

### Field meanings

| Field            | Meaning |
|------------------|---------|
| `mouth.cx` / `cy` | center where the *new* mouth will be drawn |
| `mouth.open_w` / `open_h` | base scale for mouth states (multiplied by `MOUTH_SHAPES`) |
| `mouth.box` | rectangle to erase before drawing the new mouth — covers the *original* drawn mouth |
| `left_eye` / `right_eye` | eye centers; used for blink rendering and head roll |
| `outline_color` | RGBA color for the mouth/eye lines (matches the pose's outline ink) |

`mouth.box` is **not** the visible mouth size. It's the erase patch — bigger than the new mouth, shaped to fully cover the original drawn mouth (smile dashes, oval, side strokes).

## Tagger workflow

```bash
cartoonimator tag --mascot mascots/kai --port 8801
```

Open `http://localhost:8801`.

For each pose:

1. **Point mode (P)** — click mouth center, then left eye center, then right eye center.
2. **Box mode (B)** — drag a tight rectangle around the *drawn* mouth (including any smile tails or side dashes).
3. Press **Enter** (or click Save & Next).

The tagger preserves existing anchors. Adding a mouth box later does not require retagging eyes.

### Common mistakes

- **Drawing the mouth box too tight.** It should fully cover the original mouth, including stray dashes. If old mouth pixels peek through after rendering, expand `mouth.box`.
- **Tagging the new mouth position instead of the original.** `mouth.cx/cy` is where the *new* mouth goes. `mouth.box` is where the *old* one is. They can be slightly different.
- **Skipping eye tags on tilted poses.** Eye anchors compute head roll. If you skip them, tilted-head poses get a horizontal mouth stamped on a tilted face.

## Diagnosing bad anchors

Render a face-crop sheet to see exactly what's wrong:

```bash
ffmpeg -y -i out.mp4 -vf "fps=4,crop=360:260:360:40,scale=720:-1,tile=5x4" facecrop.jpg
```

Then:

| Symptom                              | Fix                              |
|--------------------------------------|----------------------------------|
| New mouth in the wrong screen position | adjust `mouth.cx` / `mouth.cy` |
| Old mouth shows through               | expand or shift `mouth.box`     |
| Mouth is horizontal on a tilted head  | retag eye anchors                |
| Mouth too big across many poses       | scale down `mouth.open_w` / `open_h` |
| Multiple poses look identical         | confirm `pose_id` is being passed to `load_anchors` |
