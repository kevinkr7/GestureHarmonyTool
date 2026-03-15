from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np
from flask import Flask, Response

SCRIPT_DIR = Path(__file__).resolve().parent
ENGINE_ROOT = SCRIPT_DIR.parent
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

from gesture.recognizer import GestureRecognizer
from timeline.engine import TimelineEngine
from utils.logging_utils import configure_logging

app = Flask(__name__)
log = configure_logging("live_gesture")

_latest_frame_lock = threading.Lock()
_latest_jpeg: bytes | None = None
_stream_stop_event = threading.Event()
_stream_thread: threading.Thread | None = None

_timeline_lock = threading.Lock()
_timeline_engine = TimelineEngine(min_segment_s=0.3, stable_ms=200.0)
_recording_active = False
_recording_start_monotonic: float | None = None
_session_path: Path | None = None


def open_camera(camera_index: int):
    cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
    if cap.isOpened():
        return cap
    cap.release()
    return cv2.VideoCapture(camera_index)


def encode_status_frame(message: str) -> bytes:
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    frame[:] = (20, 20, 20)
    cv2.putText(frame, message, (20, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)
    ok, buffer = cv2.imencode(".jpg", frame)
    return buffer.tobytes() if ok else b""


def set_latest_frame(jpg: bytes | None) -> None:
    global _latest_jpeg
    with _latest_frame_lock:
        _latest_jpeg = jpg


def get_latest_frame() -> bytes | None:
    with _latest_frame_lock:
        return _latest_jpeg


def now_recording_ts() -> float | None:
    if not _recording_active or _recording_start_monotonic is None:
        return None
    return max(0.0, time.monotonic() - _recording_start_monotonic)


def update_timeline_realtime(degree: str) -> None:
    ts = now_recording_ts()
    if ts is None:
        return
    with _timeline_lock:
        _timeline_engine.update(degree, ts)


def finalize_timeline() -> list[dict]:
    if _session_path is None:
        return []
    end_ts = now_recording_ts() or 0.0
    with _timeline_lock:
        timeline = _timeline_engine.write(_session_path / "timeline.json", end_ts)
    log.info("timeline finalized with %d segments", len(timeline))
    return timeline


def camera_capture_loop(camera_index: int):
    recognizer = GestureRecognizer(window_size=8)
    cap = open_camera(camera_index)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    if not cap.isOpened():
        set_latest_frame(encode_status_frame("Camera unavailable"))
        while not _stream_stop_event.is_set():
            time.sleep(0.2)
        recognizer.close()
        return

    try:
        while not _stream_stop_event.is_set():
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.01)
                continue

            degree = recognizer.detect(frame)
            update_timeline_realtime(degree)

            cv2.rectangle(frame, (20, 20), (420, 110), (0, 0, 0), -1)
            cv2.putText(frame, f"Chord: {degree}", (30, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 3)

            ret, buffer = cv2.imencode('.jpg', frame)
            if ret:
                set_latest_frame(buffer.tobytes())
    finally:
        cap.release()
        recognizer.close()


def ensure_stream_worker(camera_index: int):
    global _stream_thread
    if _stream_thread and _stream_thread.is_alive():
        return
    _stream_stop_event.clear()
    _stream_thread = threading.Thread(target=camera_capture_loop, args=(camera_index,), daemon=True, name="gesture-camera")
    _stream_thread.start()


def generate_frames():
    while True:
        jpg = get_latest_frame()
        if jpg:
            yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpg + b'\r\n'
        time.sleep(0.03)


@app.route('/health')
def health():
    return {"status": "ok", "recording": _recording_active}


@app.route('/frame')
def frame():
    jpg = get_latest_frame() or encode_status_frame("Initializing stream...")
    return Response(jpg, mimetype='image/jpeg')


@app.route('/video')
def video():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/record/start', methods=['POST'])
def record_start():
    global _recording_active, _recording_start_monotonic, _timeline_engine
    with _timeline_lock:
        _timeline_engine = TimelineEngine(min_segment_s=0.3, stable_ms=200.0)
    _recording_start_monotonic = time.monotonic()
    _recording_active = True
    return {"ok": True}


@app.route('/record/stop', methods=['POST'])
def record_stop():
    global _recording_active
    _recording_active = False
    timeline = finalize_timeline()
    return {"ok": True, "segments": len(timeline)}


@app.route('/timeline')
def timeline():
    if _session_path is None:
        return Response("[]", mimetype='application/json')
    p = _session_path / "timeline.json"
    if p.exists():
        return Response(p.read_text(encoding='utf-8'), mimetype='application/json')
    return Response("[]", mimetype='application/json')


def main() -> int:
    global _session_path

    parser = argparse.ArgumentParser()
    parser.add_argument("session_path", nargs="?", help="legacy offline analysis path")
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--session-path", dest="serve_session_path", default=None)
    args = parser.parse_args()

    if args.serve:
        chosen_session = args.serve_session_path or args.session_path
        if chosen_session:
            _session_path = Path(chosen_session)
            _session_path.mkdir(parents=True, exist_ok=True)
        ensure_stream_worker(args.camera_index)
        app.run(host=args.host, port=args.port, threaded=True)
        return 0

    if not args.session_path:
        print("Usage: python live_gesture.py <session_path> OR --serve")
        return 2

    # legacy no-op analysis path (timeline is now real-time)
    session = Path(args.session_path)
    out = session / "timeline.json"
    if not out.exists():
        out.write_text(json.dumps([{"start": 0.0, "end": 1.0, "degree": "I"}], indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
