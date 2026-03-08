from __future__ import annotations

from flask import Flask, Response
import argparse
import cv2
import json
import mediapipe as mp
import os
import time
import numpy as np
from typing import Optional

app = Flask(__name__)

mp_hands = mp.solutions.hands
mp_draw = mp.solutions.drawing_utils


def chord_from_fingers(fingers_up: int) -> str:
    if fingers_up == 1:
        return "I"
    if fingers_up == 2:
        return "II"
    if fingers_up == 3:
        return "IV"
    return "NONE"


def detect_chord(frame, hands_detector) -> str:
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = hands_detector.process(rgb)

    if not results.multi_hand_landmarks:
        return "NONE"

    lms = results.multi_hand_landmarks[0]
    mp_draw.draw_landmarks(frame, lms, mp_hands.HAND_CONNECTIONS)

    def up(tip, pip):
        return lms.landmark[tip].y < lms.landmark[pip].y

    fingers = (
        up(8, 6)
        + up(12, 10)
        + up(16, 14)
        + up(20, 18)
    )

    return chord_from_fingers(fingers)


def write_timeline(session_path: str, timeline: list[dict]) -> None:
    out_path = os.path.join(session_path, "timeline.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(timeline, f, indent=2)
    print(f"Saved timeline: {out_path}")


def compress_segments(raw_segments: list[tuple[float, float, str]]) -> list[dict]:
    merged: list[dict] = []
    for start, end, degree in raw_segments:
        if degree == "NONE":
            continue
        if merged and merged[-1]["degree"] == degree and abs(start - merged[-1]["end"]) < 0.15:
            merged[-1]["end"] = end
            continue
        merged.append({"start": round(start, 3), "end": round(end, 3), "degree": degree})

    return [seg for seg in merged if seg["end"] - seg["start"] >= 0.2]


def analyze_video_session(session_path: str) -> int:
    video_path = os.path.join(session_path, "video.mp4")
    if not os.path.exists(video_path):
        print(f"Missing video: {video_path}")
        return 1

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Unable to open video: {video_path}")
        return 1

    fps = cap.get(cv2.CAP_PROP_FPS)
    fps = fps if fps and fps > 0 else 30.0

    hands = mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=1,
        min_detection_confidence=0.6,
        min_tracking_confidence=0.6,
    )

    segments: list[tuple[float, float, str]] = []
    prev_degree: Optional[str] = None
    seg_start = 0.0
    frame_idx = 0

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            t = frame_idx / fps
            degree = detect_chord(frame, hands)

            if prev_degree is None:
                prev_degree = degree
                seg_start = t
            elif degree != prev_degree:
                segments.append((seg_start, t, prev_degree))
                seg_start = t
                prev_degree = degree

            frame_idx += 1

        if prev_degree is not None:
            end_t = frame_idx / fps
            segments.append((seg_start, end_t, prev_degree))
    finally:
        cap.release()
        hands.close()

    timeline = compress_segments(segments)
    if not timeline:
        timeline = [{"start": 0.0, "end": 0.5, "degree": "I"}]

    write_timeline(session_path, timeline)
    print(f"Timeline segments: {len(timeline)}")
    return 0


def open_camera(camera_index: int):
    # Prefer DirectShow on Windows for faster + more reliable initialization.
    cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
    if cap.isOpened():
        return cap

    cap.release()
    cap = cv2.VideoCapture(camera_index)
    return cap


def encode_status_frame(message: str) -> bytes:
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    frame[:] = (20, 20, 20)
    cv2.putText(frame, "Gesture stream unavailable", (20, 220), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 200, 255), 2)
    cv2.putText(frame, message, (20, 270), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    ret, buffer = cv2.imencode('.jpg', frame)
    if not ret:
        return b""
    return buffer.tobytes()


def generate_frames(camera_index: int):
    cap = open_camera(camera_index)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    if not cap.isOpened():
        print(f"Failed to open camera index {camera_index}")
        error_jpg = encode_status_frame("Check camera permissions / index.")
        while True:
            if error_jpg:
                yield (
                    b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' + error_jpg + b'\r\n'
                )
            time.sleep(0.2)

    hands = mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=1,
        min_detection_confidence=0.6,
        min_tracking_confidence=0.6,
    )

    try:
        while True:
            success, frame = cap.read()
            if not success:
                time.sleep(0.01)
                continue

            current_chord = detect_chord(frame, hands)

            cv2.rectangle(frame, (20, 20), (350, 100), (0, 0, 0), -1)
            cv2.putText(
                frame,
                f"Chord: {current_chord}",
                (40, 75),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.2,
                (0, 255, 0),
                3,
            )

            ret, buffer = cv2.imencode('.jpg', frame)
            if not ret:
                continue
            jpg = buffer.tobytes()

            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' + jpg + b'\r\n'
            )
    finally:
        cap.release()
        hands.close()


@app.route('/')
def index():
    return """
    <!doctype html>
    <html>
      <head><meta charset=\"utf-8\"><title>Gesture Live Feedback</title></head>
      <body style=\"margin:0;background:#020617;display:flex;align-items:center;justify-content:center;min-height:100vh;\">
        <img src=\"/video\" alt=\"live feedback\" style=\"max-width:100%;max-height:100vh;\" />
      </body>
    </html>
    """


@app.route('/health')
def health():
    return {"status": "ok"}


@app.route('/video')
def video():
    return Response(generate_frames(app.config.get("camera_index", 0)),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("session_path", nargs="?", help="Session path for offline analysis")
    parser.add_argument("--serve", action="store_true", help="Run live Flask video stream")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--camera-index", type=int, default=0)
    args = parser.parse_args()

    if args.serve:
        app.config["camera_index"] = args.camera_index
        app.run(host=args.host, port=args.port, threaded=True)
        return 0

    if not args.session_path:
        print("Usage: python live_gesture.py <session_path> OR --serve")
        return 2

    return analyze_video_session(args.session_path)


if __name__ == "__main__":
    raise SystemExit(main())
