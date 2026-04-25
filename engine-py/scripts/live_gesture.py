from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
ENGINE_ROOT = SCRIPT_DIR.parent
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

from gesture.recognizer import GestureRecognizer
from timeline.engine import TimelineEngine
from utils.logging_utils import configure_logging

log = configure_logging("live_gesture")
GESTURE_LABELS = {
    "ONE": "1",
    "TWO_MINOR": "2m",
    "THREE_MINOR": "3m",
    "FOUR": "4",
}
DEFAULT_PREVIEW_FPS = 30.0
DEFAULT_GESTURE_WINDOW = 1
DEFAULT_STABLE_MS = 0.0
DEFAULT_MIN_SEGMENT_S = 0.0


def decode_mjpeg_frames(stream, chunk_size: int = 16384) -> "tuple[np.ndarray, bool]":
    buffer = bytearray()
    soi = b"\xff\xd8"
    eoi = b"\xff\xd9"
    while True:
        chunk = stream.read(chunk_size)
        if not chunk:
            break
        buffer.extend(chunk)

        while True:
            start = buffer.find(soi)
            if start < 0:
                # Keep a small trailing window to catch split SOI markers across chunks.
                if len(buffer) > 2:
                    del buffer[:-2]
                break
            if start > 0:
                del buffer[:start]

            end = buffer.find(eoi, 2)
            if end < 0:
                break

            jpg = bytes(buffer[: end + 2])
            arr = np.frombuffer(jpg, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            del buffer[: end + 2]
            if frame is not None:
                yield frame, False

    yield np.empty((0, 0, 3), dtype=np.uint8), True


def open_preview_writer(session_path: Path, width: int, height: int):
    output_path = session_path / "preview_capture.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(output_path), fourcc, 30.0, (width, height))
    if not writer.isOpened():
        raise RuntimeError(f"Unable to open preview writer at {output_path}")
    return writer


def decorate_frame(frame: np.ndarray, degree: str) -> np.ndarray:
    display_degree = GESTURE_LABELS.get(degree, "1")
    cv2.rectangle(frame, (18, 18), (560, 138), (7, 12, 25), -1)
    cv2.putText(frame, f"Detected chord: {display_degree}", (34, 72), cv2.FONT_HERSHEY_SIMPLEX, 1.05, (102, 252, 241), 3)
    cv2.putText(frame, "Gesture map: 1 | 2m | 3m | 4", (34, 118), cv2.FONT_HERSHEY_SIMPLEX, 0.82, (226, 232, 240), 2)
    return frame


def preview_mode(
    session_path: Path,
    *,
    source_fps: float = DEFAULT_PREVIEW_FPS,
    gesture_window: int = DEFAULT_GESTURE_WINDOW,
    stable_ms: float = DEFAULT_STABLE_MS,
    min_segment_s: float = DEFAULT_MIN_SEGMENT_S,
) -> int:
    recognizer = GestureRecognizer(window_size=max(1, gesture_window))
    timeline = TimelineEngine(min_segment_s=max(0.0, min_segment_s), stable_ms=max(0.0, stable_ms))
    timeline_path = session_path / "timeline.json"
    session_path.mkdir(parents=True, exist_ok=True)

    frame_index = 0
    last_flush = 0.0
    writer = None

    cv2.namedWindow("Gesture Feedback", cv2.WINDOW_NORMAL)

    try:
        for frame, eof in decode_mjpeg_frames(sys.stdin.buffer):
            if eof:
                break

            if writer is None:
                height, width = frame.shape[:2]
                writer = open_preview_writer(session_path, width, height)

            degree = recognizer.detect(frame)
            ts = frame_index / max(1.0, source_fps)
            timeline.update(degree, ts)
            frame_index += 1

            decorate_frame(frame, degree)
            writer.write(frame)
            cv2.imshow("Gesture Feedback", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

            if timeline.is_dirty and ts - last_flush >= 0.5:
                timeline.write(timeline_path, ts, pretty=False)
                last_flush = ts
    finally:
        end_ts = frame_index / max(1.0, source_fps)
        timeline.write(timeline_path, end_ts, pretty=True, force=True)
        if writer is not None:
            writer.release()
        recognizer.close()
        cv2.destroyAllWindows()

    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("session_path", nargs="?", help="Session path")
    parser.add_argument("--preview", action="store_true", help="Read MJPEG on stdin and show gesture window")
    parser.add_argument("--session-path", dest="session_path_opt", default=None)
    parser.add_argument("--source-fps", type=float, default=DEFAULT_PREVIEW_FPS)
    parser.add_argument("--gesture-window", type=int, default=DEFAULT_GESTURE_WINDOW)
    parser.add_argument("--stable-ms", type=float, default=DEFAULT_STABLE_MS)
    parser.add_argument("--min-segment-s", type=float, default=DEFAULT_MIN_SEGMENT_S)
    args = parser.parse_args()

    session = args.session_path_opt or args.session_path

    if args.preview:
        if not session:
            print("--preview requires --session-path <path>")
            return 2
        return preview_mode(
            Path(session),
            source_fps=args.source_fps,
            gesture_window=args.gesture_window,
            stable_ms=args.stable_ms,
            min_segment_s=args.min_segment_s,
        )

    if not session:
        print("Usage: python live_gesture.py <session_path> OR --preview --session-path <path>")
        return 2

    out = Path(session) / "timeline.json"
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps([{"start": 0.0, "end": 1.0, "degree": "ONE"}], indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
