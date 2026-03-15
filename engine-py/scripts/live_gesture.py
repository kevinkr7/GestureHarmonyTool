from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path

import cv2

SCRIPT_DIR = Path(__file__).resolve().parent
ENGINE_ROOT = SCRIPT_DIR.parent
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

from gesture.recognizer import GestureRecognizer
from timeline.engine import TimelineEngine
from utils.logging_utils import configure_logging

log = configure_logging("live_gesture")


def preview_mode(session_path: Path, camera_index: int = 0) -> int:
    stop_event = threading.Event()

    def stdin_watcher() -> None:
        try:
            while not stop_event.is_set():
                line = sys.stdin.readline()
                if not line:
                    break
                if line.strip().lower() in {"q", "quit", "stop", "exit"}:
                    stop_event.set()
                    break
        except Exception:
            pass

    watcher = threading.Thread(target=stdin_watcher, daemon=True, name="preview-stdin-watcher")
    watcher.start()

    cap = cv2.VideoCapture(camera_index, cv2.CAP_MSMF)
    if not cap.isOpened():
        cap.release()
        cap = cv2.VideoCapture(camera_index)

    if not cap.isOpened():
        log.error("Unable to open camera index %s", camera_index)
        return 1

    recognizer = GestureRecognizer(window_size=8)
    timeline = TimelineEngine(min_segment_s=0.3, stable_ms=200.0)
    timeline_path = session_path / "timeline.json"
    session_path.mkdir(parents=True, exist_ok=True)

    start = time.monotonic()
    last_flush = 0.0

    cv2.namedWindow("Gesture Feedback", cv2.WINDOW_NORMAL)

    try:
        while not stop_event.is_set():
            ok, frame = cap.read()
            if not ok or frame is None:
                time.sleep(0.01)
                continue

            degree = recognizer.detect(frame)
            ts = max(0.0, time.monotonic() - start)
            timeline.update(degree, ts)

            cv2.rectangle(frame, (20, 20), (420, 110), (0, 0, 0), -1)
            cv2.putText(frame, f"Chord: {degree}", (30, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 3)
            cv2.imshow("Gesture Feedback", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

            if ts - last_flush >= 0.5:
                timeline.write(timeline_path, ts)
                last_flush = ts
    finally:
        end_ts = max(0.0, time.monotonic() - start)
        timeline.write(timeline_path, end_ts)
        recognizer.close()
        cap.release()
        cv2.destroyAllWindows()

    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("session_path", nargs="?", help="Session path")
    parser.add_argument("--preview", action="store_true", help="Run OpenCV preview window")
    parser.add_argument("--session-path", dest="session_path_opt", default=None)
    parser.add_argument("--camera-index", type=int, default=0)
    args = parser.parse_args()

    session = args.session_path_opt or args.session_path

    if args.preview:
        if not session:
            print("--preview requires --session-path <path>")
            return 2
        return preview_mode(Path(session), camera_index=args.camera_index)

    if not session:
        print("Usage: python live_gesture.py <session_path> OR --preview --session-path <path>")
        return 2

    out = Path(session) / "timeline.json"
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps([{"start": 0.0, "end": 1.0, "degree": "I"}], indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
