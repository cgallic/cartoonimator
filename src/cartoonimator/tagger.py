"""Interactive face-anchor tagger for the mascot library.

Single-file HTTP server. Serves a web page that loads each character pose,
lets the user click mouth/eye points and draw a full mouth box per pose, saves
to `<mascot>/anchors.json` (with `default` + `per_pose` sections).

Run on the host where pose PNGs live:
    cartoonimator tag --mascot path/to/mascots/kai --port 8801
Open http://localhost:8801/ (SSH-forward the port if running remotely).
"""
from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HTML_PAGE = r"""<!DOCTYPE html>
<html>
<head>
<title>Cartoonimator Anchor Tagger</title>
<style>
  body { background:#12121A; color:#eee; font-family:-apple-system,system-ui,sans-serif;
         margin:0; padding:20px; }
  header { display:flex; gap:24px; align-items:center; margin-bottom:16px; }
  select, button { background:#1f1f2e; color:#fff; border:1px solid #3a3a5a;
                   padding:8px 12px; font-size:14px; border-radius:6px; cursor:pointer; }
  button:hover { background:#2a2a44; }
  .status { font-size:14px; opacity:0.85; }
  .stage { display:flex; gap:24px; align-items:flex-start; }
  .canvas-wrap { background:#000; padding:0; border:1px solid #3a3a5a; }
  canvas { display:block; cursor:crosshair; }
  .panel { width:320px; background:#1a1a26; padding:16px; border-radius:8px;
           border:1px solid #2a2a44; }
  .panel h3 { margin:0 0 8px 0; font-size:13px; opacity:0.7;
              text-transform:uppercase; letter-spacing:0.05em; }
  .legend-row { display:flex; align-items:center; gap:8px; margin:6px 0;
                font-size:13px; }
  .dot { width:12px; height:12px; border-radius:50%; }
  .actions button { width:100%; margin-top:8px; }
  .hint { font-size:12px; color:#FFD86B; margin-top:8px; line-height:1.4; }
  .nav-grid { display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:8px; }
  .nav-grid button { width:100%; margin-top:0; }
  .jump-row { display:flex; gap:8px; margin-top:8px; }
  .jump-row input { min-width:0; flex:1; background:#10101A; color:#fff;
                    border:1px solid #3a3a5a; border-radius:6px; padding:8px; }
  .jump-row button { width:auto; margin-top:0; }
  .progress { font-size:12px; opacity:0.7; margin-top:8px; }
  .keymap { font-size:11px; opacity:0.6; margin-top:12px; line-height:1.6; }
  .pose-id { font-family:monospace; font-size:13px; color:#A8C4FF; margin:8px 0; }
  .saved-mark { color:#5EFF8A; font-weight:bold; }
  .mode-row { display:flex; gap:8px; margin:8px 0 12px; }
  .mode-row button { flex:1; padding:7px 8px; }
  .mode-row button.active { background:#3454FF; border-color:#6D84FF; }
  code { color:#A8C4FF; }
</style>
</head>
<body>
<header>
  <strong>Cartoonimator Anchor Tagger</strong>
  <span class="status" id="status">loading…</span>
</header>

<div class="stage">
  <div class="canvas-wrap">
    <canvas id="canvas" width="1024" height="1024"></canvas>
  </div>
  <div class="panel">
    <h3>Current pose</h3>
    <div class="pose-id" id="pose-id">—</div>
    <div class="progress" id="progress">—</div>

    <h3 style="margin-top:16px">Mode</h3>
    <div class="mode-row">
      <button id="point-mode-btn" class="active">Points</button>
      <button id="box-mode-btn">Mouth box</button>
    </div>

    <h3>Points</h3>
    <div class="legend-row"><div class="dot" style="background:#FF4444"></div>
      1. Mouth center <span id="m-status"></span></div>
    <div class="legend-row"><div class="dot" style="background:#22EE55"></div>
      2. Left eye center <span id="le-status"></span></div>
    <div class="legend-row"><div class="dot" style="background:#22BBFF"></div>
      3. Right eye center <span id="re-status"></span></div>

    <h3 style="margin-top:16px">Mouth erase box</h3>
    <div class="legend-row"><div class="dot" style="background:#FFCC33; border-radius:0"></div>
      Drag around full mouth only <span id="box-status"></span></div>

    <div class="actions">
      <button id="save-btn">Save & Next →</button>
      <button id="reset-btn">Clear points only</button>
      <button id="clear-box-btn">Clear mouth box</button>
      <button id="skip-btn">Skip (use default)</button>
      <div class="nav-grid">
        <button id="first-btn">First</button>
        <button id="prev-btn">Previous</button>
        <button id="next-btn">Next</button>
        <button id="last-btn">Last</button>
      </div>
      <div class="jump-row">
        <input id="jump-input" type="number" min="1" placeholder="Pose #">
        <button id="jump-btn">Go</button>
      </div>
    </div>

    <div class="keymap">
      <strong>Keys:</strong><br>
      Enter — Save & Next<br>
      B — Mouth box mode<br>
      P — Point mode<br>
      R — Reset<br>
      S — Skip<br>
      Home / End — First / Last<br>
      ← / → — Prev / Next
    </div>
  </div>
</div>

<script>
let defaultAnchors = {};
let poses = [];
let poseIdx = 0;
let perPose = {};
let clicks = [];
let mouthBox = null;
let liveBox = null;
let mode = 'points';
let isDraggingBox = false;
let boxStart = null;
let currentImage = null;

const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');
const statusEl = document.getElementById('status');
const poseIdEl = document.getElementById('pose-id');
const progressEl = document.getElementById('progress');
const mStatus = document.getElementById('m-status');
const leStatus = document.getElementById('le-status');
const reStatus = document.getElementById('re-status');
const boxStatus = document.getElementById('box-status');
const pointModeBtn = document.getElementById('point-mode-btn');
const boxModeBtn = document.getElementById('box-mode-btn');
const jumpInput = document.getElementById('jump-input');

async function init() {
  const r = await fetch('/api/poses');
  const data = await r.json();
  poses = data.poses;
  defaultAnchors = data.default || {};
  perPose = data.per_pose || {};
  poseIdx = 0;
  for (let i = 0; i < poses.length; i++) {
    const entry = poses[i] === 'base' ? defaultAnchors : perPose[poses[i]];
    if (!entry?.mouth?.box) { poseIdx = i; break; }
  }
  loadPose();
}

function pointFromAnchor(anchor) {
  if (!anchor) return null;
  if (Array.isArray(anchor)) return anchor;
  if (Number.isFinite(anchor.cx) && Number.isFinite(anchor.cy)) return [anchor.cx, anchor.cy];
  return null;
}

function boxFromAnchor(anchor) {
  if (!anchor?.box) return null;
  const box = anchor.box;
  if (!Number.isFinite(box.x) || !Number.isFinite(box.y) ||
      !Number.isFinite(box.w) || !Number.isFinite(box.h)) return null;
  return { x: box.x, y: box.y, w: box.w, h: box.h };
}

function validPoint(point) {
  if (!Array.isArray(point) || point.length < 2) return null;
  const x = Number(point[0]);
  const y = Number(point[1]);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
  return [x, y];
}

function loadPose() {
  if (poseIdx < 0) poseIdx = 0;
  if (poseIdx >= poses.length) poseIdx = poses.length - 1;
  const id = poses[poseIdx];
  const hasAnchors = id === 'base' ? !!defaultAnchors?.mouth : !!perPose[id];
  const saved = id === 'base' ? (defaultAnchors || {}) : (perPose[id] || {});
  const hasBox = !!saved?.mouth?.box;
  poseIdEl.innerHTML = id + (hasBox ? ' <span class="saved-mark">box ✓</span>' : (hasAnchors ? ' <span class="saved-mark">anchors ✓</span>' : ''));
  const anchorCount = Object.keys(perPose).length + (defaultAnchors?.mouth ? 1 : 0);
  const boxCount = poses.filter(p => (p === 'base' ? defaultAnchors : perPose[p])?.mouth?.box).length;
  progressEl.textContent = `${boxCount}/${poses.length} mouth boxes | ${anchorCount}/${poses.length} anchors | viewing ${poseIdx+1} of ${poses.length}`;
  jumpInput.value = String(poseIdx + 1);
  clicks = [
    pointFromAnchor(saved.mouth) || pointFromAnchor(defaultAnchors.mouth),
    pointFromAnchor(saved.left_eye) || pointFromAnchor(defaultAnchors.left_eye),
    pointFromAnchor(saved.right_eye) || pointFromAnchor(defaultAnchors.right_eye),
  ].filter(Boolean);
  mouthBox = boxFromAnchor(saved.mouth);
  reloadCanvas();
  updateClickStatus();
}

function setMode(nextMode) {
  mode = nextMode;
  pointModeBtn.classList.toggle('active', mode === 'points');
  boxModeBtn.classList.toggle('active', mode === 'box');
  canvas.style.cursor = 'crosshair';
  statusEl.textContent = mode === 'box'
    ? 'mouth box mode: drag tightly around the drawn mouth; eyes are preserved'
    : 'point mode: mouth center, left eye, right eye';
}

function imagePoint(e) {
  const rect = canvas.getBoundingClientRect();
  return [
    Math.round((e.clientX - rect.left) * (canvas.width / rect.width)),
    Math.round((e.clientY - rect.top) * (canvas.height / rect.height)),
  ];
}

function reloadCanvas() {
  currentImage = new Image();
  currentImage.onload = drawCanvas;
  currentImage.src = `/image/${poses[poseIdx]}.png?t=${Date.now()}`;
}

function drawCanvas() {
  ctx.clearRect(0,0,1024,1024);
  if (currentImage) ctx.drawImage(currentImage,0,0);
  drawOverlay();
}

function drawOverlay() {
  const boxToDraw = liveBox || mouthBox;
  if (boxToDraw) {
    ctx.strokeStyle = '#FFCC33';
    ctx.lineWidth = 6;
    ctx.fillStyle = 'rgba(255,204,51,0.15)';
    ctx.fillRect(boxToDraw.x, boxToDraw.y, boxToDraw.w, boxToDraw.h);
    ctx.setLineDash([14, 8]);
    ctx.strokeRect(boxToDraw.x, boxToDraw.y, boxToDraw.w, boxToDraw.h);
    ctx.setLineDash([]);
    ctx.strokeStyle = '#111';
    ctx.lineWidth = 2;
    ctx.strokeRect(boxToDraw.x, boxToDraw.y, boxToDraw.w, boxToDraw.h);
  }

  const colors = ['#FF4444', '#22EE55', '#22BBFF'];
  for (let i = 0; i < clicks.length; i++) {
    const point = validPoint(clicks[i]);
    if (!point) continue;
    const [x, y] = point;
    ctx.strokeStyle = colors[i] || '#FFFFFF';
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(x-12, y); ctx.lineTo(x+12, y);
    ctx.moveTo(x, y-12); ctx.lineTo(x, y+12);
    ctx.stroke();
  }
}

function updateClickStatus() {
  const mouthPoint = validPoint(clicks[0]);
  const leftEyePoint = validPoint(clicks[1]);
  const rightEyePoint = validPoint(clicks[2]);
  mStatus.textContent  = mouthPoint ? `(${mouthPoint[0]}, ${mouthPoint[1]})` : '';
  leStatus.textContent = leftEyePoint ? `(${leftEyePoint[0]}, ${leftEyePoint[1]})` : '';
  reStatus.textContent = rightEyePoint ? `(${rightEyePoint[0]}, ${rightEyePoint[1]})` : '';
  const boxForStatus = liveBox || mouthBox;
  boxStatus.textContent = boxForStatus ? `(${boxForStatus.x}, ${boxForStatus.y}, ${boxForStatus.w}×${boxForStatus.h})` : '';
}

canvas.addEventListener('click', (e) => {
  if (mode !== 'points') return;
  if (clicks.length >= 3) clicks = [];
  const [x, y] = imagePoint(e);
  clicks.push([x, y]);
  drawCanvas();
  updateClickStatus();
});

canvas.addEventListener('mousedown', (e) => {
  if (mode !== 'box') return;
  isDraggingBox = true;
  boxStart = imagePoint(e);
  liveBox = { x: boxStart[0], y: boxStart[1], w: 0, h: 0 };
  drawCanvas();
  updateClickStatus();
});

canvas.addEventListener('mousemove', (e) => {
  if (mode !== 'box' || !isDraggingBox || !boxStart) return;
  const [x, y] = imagePoint(e);
  liveBox = {
    x: Math.min(boxStart[0], x),
    y: Math.min(boxStart[1], y),
    w: Math.abs(x - boxStart[0]),
    h: Math.abs(y - boxStart[1]),
  };
  drawCanvas();
  updateClickStatus();
});

canvas.addEventListener('mouseup', () => {
  if (mode !== 'box') return;
  isDraggingBox = false;
  boxStart = null;
  if (liveBox && liveBox.w > 0 && liveBox.h > 0) {
    mouthBox = liveBox;
  }
  liveBox = null;
  drawCanvas();
  updateClickStatus();
});

pointModeBtn.onclick = () => setMode('points');
boxModeBtn.onclick = () => setMode('box');
document.getElementById('reset-btn').onclick = () => { clicks = []; drawCanvas(); updateClickStatus(); };
document.getElementById('clear-box-btn').onclick = () => { mouthBox = null; liveBox = null; drawCanvas(); updateClickStatus(); };
document.getElementById('skip-btn').onclick = () => { poseIdx++; loadPose(); };
document.getElementById('prev-btn').onclick = () => { poseIdx--; loadPose(); };
document.getElementById('next-btn').onclick = () => { poseIdx++; loadPose(); };
document.getElementById('first-btn').onclick = () => { poseIdx = 0; loadPose(); };
document.getElementById('last-btn').onclick = () => { poseIdx = poses.length - 1; loadPose(); };
document.getElementById('jump-btn').onclick = () => {
  const n = parseInt(jumpInput.value, 10);
  if (!Number.isFinite(n)) return;
  poseIdx = Math.max(0, Math.min(poses.length - 1, n - 1));
  loadPose();
};
document.getElementById('save-btn').onclick = async () => {
  if (clicks.length !== 3) { statusEl.textContent = 'missing mouth/eye anchors; existing eyes load automatically, otherwise use point mode once'; return; }
  const payload = {
    pose_id: poses[poseIdx],
    mouth: clicks[0],
    mouth_box: mouthBox,
    left_eye: clicks[1],
    right_eye: clicks[2],
  };
  const r = await fetch('/api/save', { method:'POST', headers:{'Content-Type':'application/json'},
                                       body: JSON.stringify(payload) });
  if (r.ok) {
    const saved = await r.json();
    if (poses[poseIdx] === 'base') defaultAnchors = saved.entry;
    else perPose[poses[poseIdx]] = saved.entry;
    statusEl.textContent = `saved ${poses[poseIdx]}`;
    poseIdx++; loadPose();
  } else {
    statusEl.textContent = 'save failed: ' + (await r.text());
  }
};

document.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') document.getElementById('save-btn').click();
  else if (e.key === 'b' || e.key === 'B') setMode('box');
  else if (e.key === 'p' || e.key === 'P') setMode('points');
  else if (e.key === 'r' || e.key === 'R') document.getElementById('reset-btn').click();
  else if (e.key === 's' || e.key === 'S') document.getElementById('skip-btn').click();
  else if (e.key === 'Home') document.getElementById('first-btn').click();
  else if (e.key === 'End') document.getElementById('last-btn').click();
  else if (e.key === 'ArrowLeft') document.getElementById('prev-btn').click();
  else if (e.key === 'ArrowRight') document.getElementById('next-btn').click();
});

init();
</script>
</body>
</html>
"""


def _list_poses(mascot_root: Path) -> list[str]:
    poses_dir = mascot_root / "poses"
    if not poses_dir.is_dir():
        return []
    poses = [p.stem for p in sorted(poses_dir.glob("*.png"))]
    if (mascot_root / "base.png").is_file():
        return ["base"] + poses
    return poses


def _read_anchors(mascot_root: Path) -> dict:
    path = mascot_root / "anchors.json"
    if not path.exists():
        return {"image_size": [1024, 1024], "default": {}, "per_pose": {}}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if "per_pose" in raw:
        return raw
    return {
        "image_size": raw.get("image_size", [1024, 1024]),
        "default": {
            "mouth": raw.get("mouth"),
            "left_eye": raw.get("left_eye"),
            "right_eye": raw.get("right_eye"),
            "outline_color": raw.get("outline_color", [26, 26, 46, 255]),
        },
        "per_pose": {},
    }


def _write_anchors(mascot_root: Path, data: dict) -> None:
    path = mascot_root / "anchors.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _point_xy(value: object) -> tuple[int, int] | None:
    if isinstance(value, list) and len(value) >= 2:
        return int(value[0]), int(value[1])
    if isinstance(value, dict) and "cx" in value and "cy" in value:
        return int(value["cx"]), int(value["cy"])
    return None


def _valid_box(value: object) -> dict | None:
    if not isinstance(value, dict):
        return None
    try:
        x = int(value["x"])
        y = int(value["y"])
        w = int(value["w"])
        h = int(value["h"])
    except (KeyError, TypeError, ValueError):
        return None
    if w <= 0 or h <= 0:
        return None
    return {"x": x, "y": y, "w": w, "h": h}


def _make_handler(mascot_root: Path) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:  # quiet
            sys.stderr.write(f"[tagger] {format % args}\n")

        def _send_json(self, code: int, body: dict | list) -> None:
            payload = json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:  # noqa: N802
            url = urlparse(self.path)
            p = url.path
            if p == "/" or p == "/index.html":
                body = HTML_PAGE.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if p == "/api/poses":
                anchors = _read_anchors(mascot_root)
                self._send_json(200, {
                    "poses": _list_poses(mascot_root),
                    "default": anchors.get("default", {}),
                    "per_pose": anchors.get("per_pose", {}),
                })
                return
            if p.startswith("/image/"):
                fname = p.removeprefix("/image/")
                if fname == "base.png":
                    src = mascot_root / "base.png"
                else:
                    src = mascot_root / "poses" / fname
                if not src.is_file():
                    self.send_error(404, f"not found: {src}")
                    return
                data = src.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(data)
                return
            self.send_error(404, f"unknown: {p}")

        def do_POST(self) -> None:  # noqa: N802
            url = urlparse(self.path)
            if url.path != "/api/save":
                self.send_error(404, "unknown POST")
                return
            length = int(self.headers.get("Content-Length") or "0")
            body = self.rfile.read(length).decode("utf-8")
            try:
                payload = json.loads(body)
            except json.JSONDecodeError as e:
                self.send_error(400, f"invalid JSON: {e}")
                return
            pose_id = payload.get("pose_id")
            if not pose_id:
                self.send_error(400, "missing pose_id")
                return
            anchors = _read_anchors(mascot_root)
            is_base = pose_id == "base"
            existing = (
                anchors.get("default", {}) if is_base
                else anchors.get("per_pose", {}).get(pose_id, {})
            )
            defaults = anchors.get("default", {})
            existing_mouth = existing.get("mouth", {}) or {}
            existing_le = existing.get("left_eye", {}) or {}
            existing_re = existing.get("right_eye", {}) or {}

            mouth_xy = (
                _point_xy(payload.get("mouth"))
                or _point_xy(existing_mouth)
                or _point_xy(defaults.get("mouth", {}))
            )
            le_xy = (
                _point_xy(payload.get("left_eye"))
                or _point_xy(existing_le)
                or _point_xy(defaults.get("left_eye", {}))
            )
            re_xy = (
                _point_xy(payload.get("right_eye"))
                or _point_xy(existing_re)
                or _point_xy(defaults.get("right_eye", {}))
            )
            if mouth_xy is None or le_xy is None or re_xy is None:
                self.send_error(400, "missing mouth/eye anchors")
                return

            mouth_w = existing_mouth.get("open_w", defaults.get("mouth", {}).get("open_w", 28))
            mouth_h = existing_mouth.get("open_h", defaults.get("mouth", {}).get("open_h", 14))
            eye_w = existing_le.get("w", defaults.get("left_eye", {}).get("w", 18))
            eye_h = existing_le.get("h", defaults.get("left_eye", {}).get("h", 12))
            mouth_payload = {
                "cx": mouth_xy[0], "cy": mouth_xy[1],
                "open_w": mouth_w, "open_h": mouth_h,
            }
            if "mouth_box" in payload:
                box = _valid_box(payload.get("mouth_box"))
                if box:
                    mouth_payload["box"] = box
            elif isinstance(existing_mouth, dict) and existing_mouth.get("box"):
                box = _valid_box(existing_mouth.get("box"))
                if box:
                    mouth_payload["box"] = box
            anchors.setdefault("image_size", [1024, 1024])
            anchors.setdefault("per_pose", {})
            entry = {
                "mouth": mouth_payload,
                "left_eye": {"cx": le_xy[0], "cy": le_xy[1], "w": eye_w, "h": eye_h},
                "right_eye": {"cx": re_xy[0], "cy": re_xy[1], "w": eye_w, "h": eye_h},
            }
            if is_base:
                entry["outline_color"] = defaults.get("outline_color", [26, 26, 46, 255])
                anchors["default"] = entry
            else:
                anchors["per_pose"][pose_id] = entry
            _write_anchors(mascot_root, anchors)
            self._send_json(200, {"ok": True, "entry": entry})

    return Handler


def serve(mascot_root: str | Path, port: int = 8801, bind: str = "0.0.0.0") -> None:
    """Start the tagger HTTP server. Blocks until interrupted."""
    root = Path(mascot_root)
    if not root.is_dir():
        raise FileNotFoundError(f"mascot directory not found: {root}")
    server = ThreadingHTTPServer((bind, port), _make_handler(root))
    print(f"[tagger] mascot: {root}", file=sys.stderr)
    print(f"[tagger] listening on http://{bind}:{port}/", file=sys.stderr)
    server.serve_forever()


def main() -> int:
    p = argparse.ArgumentParser(prog="cartoonimator-tag")
    p.add_argument("--mascot", required=True, help="path to mascot directory")
    p.add_argument("--port", type=int, default=8801)
    p.add_argument("--bind", default="0.0.0.0")
    args = p.parse_args()
    serve(args.mascot, port=args.port, bind=args.bind)
    return 0


if __name__ == "__main__":
    sys.exit(main())
