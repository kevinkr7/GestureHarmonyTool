import cv2
import json
import time
from ui.hud import HUDRenderer
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QComboBox, QPushButton, QFrame, QSizePolicy, QDialog, QDialogButtonBox, QGridLayout
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
import subprocess
import threading
import re
from pathlib import Path
from datetime import datetime
from core.gesture.recognizer import GestureRecognizer
from core.timeline.engine import TimelineEngine
from core.scripts.live_gesture import decode_mjpeg_frames
from core.engine.vst_renderer import main as render_vst

# ---------------------------------------------------------------------------
# Preview resolution fed to the MJPEG pipe (and thus to MediaPipe).
# The saved video.mp4 is always recorded at full camera resolution.
# Lower values → faster gesture inference, lower latency preview.
# ---------------------------------------------------------------------------
PREVIEW_W = 960
PREVIEW_H = 540

APP_STYLE = """
/* Global */
QWidget {
    font-family: "Segoe UI Variable", "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    color: #E2E8F0;
    font-size: 14px;
}

QLabel {
    background: transparent;
}

QMainWindow, QDialog {
    background-color: #0F1117;
}

/* Cards / Panels */
QFrame#card {
    background-color: #171B24;
    border: 1px solid #2A3140;
    border-radius: 12px;
}

/* Typography */
QLabel#title {
    font-size: 24px;
    font-weight: 600;
    color: #F8FAFC;
    margin-bottom: 4px;
}

QLabel#subtitle {
    font-size: 14px;
    color: #94A3B8;
    margin-bottom: 16px;
}

QLabel#statusReady {
    color: #10B981;
    font-weight: 600;
}

QLabel#statusRecording {
    color: #EF4444;
    font-weight: 600;
}

QLabel#statusProcessing {
    color: #F59E0B;
    font-weight: 600;
}

/* Buttons */
QPushButton {
    background-color: #1D2330;
    border: 1px solid #2A3140;
    border-radius: 6px;
    padding: 8px 16px;
    color: #F8FAFC;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #2A3140;
    border: 1px solid #3B4252;
}

QPushButton:pressed {
    background-color: #171B24;
}

QPushButton:disabled {
    background-color: #1D2330;
    color: #475569;
    border: 1px solid #1D2330;
}

QPushButton#primaryAction {
    background-color: #2563EB;
    border: none;
}

QPushButton#primaryAction:hover {
    background-color: #3B82F6;
}

QPushButton#primaryAction:pressed {
    background-color: #1D4ED8;
}

QPushButton#primaryAction:disabled {
    background-color: #1D2330;
    color: #475569;
}

QPushButton#dangerAction {
    background-color: transparent;
    border: 1px solid #991B1B;
    color: #FCA5A5;
}

QPushButton#dangerAction:hover {
    background-color: #7F1D1D;
    color: #FEF2F2;
}

QPushButton#dangerAction:pressed {
    background-color: #450A0A;
}

QPushButton#dangerAction:disabled {
    border: 1px solid #475569;
    color: #475569;
}

/* Dropdowns */
QComboBox {
    background-color: #1D2330;
    border: 1px solid #2A3140;
    border-radius: 6px;
    padding: 8px 12px;
    color: #F8FAFC;
}

QComboBox:hover {
    border: 1px solid #3B4252;
}

QComboBox:focus {
    border: 1px solid #2563EB;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox::down-arrow {
    image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%2394A3B8' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><path d='m6 9 6 6 6-6'/></svg>");
}

QComboBox QAbstractItemView {
    background-color: #1D2330;
    border: 1px solid #2A3140;
    selection-background-color: #2A3140;
    selection-color: #F8FAFC;
    border-radius: 6px;
    outline: none;
    padding: 4px;
}
"""

class MappingDialog(QDialog):
    def __init__(self, parent=None, current_mapping=None):
        super().__init__(parent)
        self.setWindowTitle("Configure Manual Mapping")
        self.setModal(True)
        self.setStyleSheet(APP_STYLE)
        self.mappings_ui = {}
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        
        title = QLabel("Chord Mapping Configuration")
        title.setObjectName("title")
        layout.addWidget(title)
        
        grid = QGridLayout()
        grid.setSpacing(16)
        
        gestures = [("ONE", "Finger 1"), ("TWO_MINOR", "Finger 2"), ("THREE_MINOR", "Finger 3"), ("FOUR", "Finger 4")]
        for row, (key, label) in enumerate(gestures):
            lbl = QLabel(label)
            root_combo = QComboBox()
            root_combo.setFixedWidth(80)
            root_combo.addItems(["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"])
            ext_combo = QComboBox()
            ext_combo.setFixedWidth(120)
            ext_combo.addItems(["Major", "Minor", "Sus2", "Sus4", "7", "m7", "Diminished", "Augmented"])
            
            if current_mapping and key in current_mapping:
                root_combo.setCurrentText(current_mapping[key][0])
                ext_combo.setCurrentText(current_mapping[key][1])
                
            grid.addWidget(lbl, row, 0)
            grid.addWidget(root_combo, row, 1)
            grid.addWidget(ext_combo, row, 2)
            self.mappings_ui[key] = (root_combo, ext_combo)
            
        layout.addLayout(grid)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def get_mappings(self):
        result = {}
        for k, (rcb, ecb) in self.mappings_ui.items():
            result[k] = (rcb.currentText(), ecb.currentText())
        return result

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gesture Harmony Tool")
        self.setMinimumSize(1000, 700)
        self.setStyleSheet(APP_STYLE)
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(24, 24, 24, 24)
        self.main_layout.setSpacing(16)
        
        self.setup_header()
        self.setup_controls()
        self.setup_preview()
        
        self.camera_thread = None
        # Frame-drop flag: True while a queued frame is waiting to be painted.
        self._display_pending = False
        
    def setup_header(self):
        self.title_label = QLabel("Gesture Harmony Tool")
        self.title_label.setObjectName("title")
        
        self.subtitle_label = QLabel("Gestures: 1 finger = 1, 2 fingers = 2m, 3 fingers = 3m, 4 fingers = 4")
        self.subtitle_label.setObjectName("subtitle")
        
        self.main_layout.addWidget(self.title_label)
        self.main_layout.addWidget(self.subtitle_label)

    def setup_controls(self):
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setSpacing(12)
        
        self.camera_combo = QComboBox()
        self.camera_combo.setMinimumWidth(150)
        self.mic_combo = QComboBox()
        self.mic_combo.setMinimumWidth(150)
        
        self.populate_devices()
        
        toolbar_layout.addWidget(QLabel("Camera:"))
        toolbar_layout.addWidget(self.camera_combo)
        toolbar_layout.addWidget(QLabel("Mic:"))
        toolbar_layout.addWidget(self.mic_combo)
        
        toolbar_layout.addWidget(QLabel("Mapping:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Automatic", "Manual"])
        self.mode_combo.currentTextChanged.connect(self.on_mode_changed)
        toolbar_layout.addWidget(self.mode_combo)
        
        self.config_btn = QPushButton("⚙ Configure")
        self.config_btn.setVisible(False)
        self.config_btn.clicked.connect(self.open_mapping_dialog)
        toolbar_layout.addWidget(self.config_btn)
        
        toolbar_layout.addStretch()
        
        self.start_btn = QPushButton("🔴 Start Recording")
        self.start_btn.setObjectName("primaryAction")
        self.start_btn.clicked.connect(self.start_recording)
        
        self.stop_btn = QPushButton("⏹ Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_recording)
        
        self.cancel_btn = QPushButton("✕ Cancel")
        self.cancel_btn.setObjectName("dangerAction")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_recording)
        
        toolbar_layout.addWidget(self.start_btn)
        toolbar_layout.addWidget(self.stop_btn)
        toolbar_layout.addWidget(self.cancel_btn)
        
        self.main_layout.addLayout(toolbar_layout)
        
        self.current_manual_mappings = {
            "ONE": ("C", "Major"),
            "TWO_MINOR": ("D", "Minor"),
            "THREE_MINOR": ("E", "Minor"),
            "FOUR": ("F", "Major")
        }

    def on_mode_changed(self, mode):
        self.config_btn.setVisible(mode == "Manual")
        
    def open_mapping_dialog(self):
        dialog = MappingDialog(self, self.current_manual_mappings)
        if dialog.exec():
            self.current_manual_mappings = dialog.get_mappings()

    def setup_preview(self):
        self.preview_card = QFrame()
        self.preview_card.setObjectName("card")
        self.preview_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        preview_layout = QVBoxLayout(self.preview_card)
        preview_layout.setContentsMargins(16, 16, 16, 16)
        
        self.video_label = QLabel("Preview will appear here")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setStyleSheet("color: #475569; font-size: 18px;")
        
        preview_layout.addWidget(self.video_label)
        
        self.video_widget = QVideoWidget()
        self.video_widget.setVisible(False)
        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget)
        preview_layout.addWidget(self.video_widget)
        
        self.play_btn = QPushButton("⏯ Play Video")
        self.play_btn.setObjectName("primaryAction")
        self.play_btn.setVisible(False)
        self.play_btn.clicked.connect(self.toggle_play)
        preview_layout.addWidget(self.play_btn)
        
        self.main_layout.addWidget(self.preview_card)
        
        # Status Bar
        self.status_label = QLabel("🟢 Ready. Select devices and start recording.")
        self.status_label.setObjectName("statusReady")
        self.main_layout.addWidget(self.status_label)

    def toggle_play(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
            self.play_btn.setText("⏯ Play Video")
        else:
            self.media_player.play()
            self.play_btn.setText("⏸ Pause Video")

    def populate_devices(self):
        try:
            res = subprocess.run(
                ["ffmpeg", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
            )
            # Ffmpeg prints list_devices to stderr/stdout mixed
            video_devices = []
            audio_devices = []
            
            for line in res.stdout.splitlines():
                # [dshow @ ...] "Device Name" (video/audio)
                match = re.search(r'"([^"]+)" \((video|audio)\)', line)
                if match:
                    name = match.group(1)
                    type_ = match.group(2)
                    if type_ == "video":
                        video_devices.append(name)
                    elif type_ == "audio":
                        audio_devices.append(name)
            
            if video_devices:
                self.camera_combo.addItems(video_devices)
            else:
                self.camera_combo.addItem("No Camera Found")
                
            if audio_devices:
                self.mic_combo.addItems(audio_devices)
            else:
                self.mic_combo.addItem("No Mic Found")
                
        except Exception as e:
            print(f"Error parsing devices: {e}")
            self.camera_combo.addItem("Default Camera")
            self.mic_combo.addItem("Default Mic")

    def start_recording(self):
        self.status_label.setText("🔴 Recording...")
        self.status_label.setObjectName("statusRecording")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.cancel_btn.setEnabled(True)
        
        cam_name = self.camera_combo.currentText()
        mic_name = self.mic_combo.currentText()
        
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.current_session = Path("sessions") / f"session_{session_id}"
        self.current_session.mkdir(parents=True, exist_ok=True)
        
        # Write chord preferences
        prefs = {"mode": self.mode_combo.currentText().lower()}
        if prefs["mode"] == "manual":
            mappings = {}
            for g_key, (root_str, ext_str) in self.current_manual_mappings.items():
                root_semitone = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"].index(root_str)
                intervals = {
                    "Major": [0, 4, 7],
                    "Minor": [0, 3, 7],
                    "Sus2": [0, 2, 7],
                    "Sus4": [0, 5, 7],
                    "7": [0, 4, 7, 10],
                    "m7": [0, 3, 7, 10],
                    "Diminished": [0, 3, 6],
                    "Augmented": [0, 4, 8]
                }[ext_str]
                mappings[g_key] = {
                    "root_semitone": root_semitone,
                    "intervals": intervals,
                    "label": f"{root_str} {ext_str}"
                }
            prefs["mappings"] = mappings
            prefs["key"] = {"root_note": 48, "scale_type": "major"}
            
        with open(self.current_session / "chord_preferences.json", "w", encoding="utf-8") as f:
            json.dump(prefs, f, indent=2)
            
        self.video_widget.setVisible(False)
        self.play_btn.setVisible(False)
        self.video_label.setVisible(True)
        self.media_player.stop()
        
        video_out = self.current_session / "video.mp4"

        # -------------------------------------------------------------------
        # FFmpeg command — optimised for minimum latency
        #
        # Key changes vs original:
        #   * -fflags nobuffer -flags low_delay -probesize 32: eliminate
        #     FFmpeg's internal buffering before it releases the first frame.
        #   * -rtbufsize 100M -thread_queue_size 512: large ring buffer so
        #     dshow never drops frames due to queue starvation.
        #   * Output 1 (mp4): full resolution, saves at original quality.
        #   * Output 2 (MJPEG pipe): scaled down to PREVIEW_W×PREVIEW_H and
        #     quality 8 (vs original 5) — the lower resolution dramatically
        #     speeds up MediaPipe inference; quality 8 is still sharp enough
        #     for gesture detection.
        # -------------------------------------------------------------------
        cmd = [
            "ffmpeg", "-y",
            # Low-latency capture flags
            "-fflags", "nobuffer",
            "-flags", "low_delay",
            "-probesize", "32",
            "-rtbufsize", "100M",
            "-thread_queue_size", "512",
            # DirectShow input
            "-f", "dshow",
            "-i", f"video={cam_name}:audio={mic_name}",
            # Output 1: full-resolution H.264 mp4 file (saved recording)
            "-map", "0:v", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-c:a", "aac",
            str(video_out),
            # Output 2: low-res MJPEG pipe for real-time preview + gesture
            "-map", "0:v", "-an",
            "-vf", f"fps=30,scale={PREVIEW_W}:{PREVIEW_H}",
            "-c:v", "mjpeg", "-q:v", "8",
            "-f", "mjpeg", "pipe:1"
        ]
        
        self.ffmpeg_proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        
        mode = self.mode_combo.currentText().lower()
        if mode == "manual":
            mappings = {k: f"{root} {ext}" for k, (root, ext) in self.current_manual_mappings.items()}
        else:
            mappings = {"ONE": "C Major", "TWO_MINOR": "D Minor", "THREE_MINOR": "E Minor", "FOUR": "F Major"}
            
        self.camera_thread = CameraThread(self.ffmpeg_proc.stdout, self.current_session, mappings)
        self.camera_thread.frame_ready.connect(self.update_preview, Qt.ConnectionType.QueuedConnection)
        self.camera_thread.start()

    def stop_recording(self):
        self.status_label.setText("⚙ Processing... generating harmonized audio in REAPER.")
        self.status_label.setObjectName("statusProcessing")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        if self.camera_thread:
            self.camera_thread.stop()
            self.camera_thread.wait()
            self.camera_thread = None
            
        if hasattr(self, 'ffmpeg_proc') and self.ffmpeg_proc:
            if self.ffmpeg_proc.poll() is None:
                try:
                    if self.ffmpeg_proc.stdin:
                        self.ffmpeg_proc.stdin.write(b'q\n')
                        self.ffmpeg_proc.stdin.flush()
                    
                    def drain():
                        self.ffmpeg_proc.stdout.read()
                    threading.Thread(target=drain, daemon=True).start()
                    
                    self.ffmpeg_proc.wait(timeout=5)
                except Exception:
                    self.ffmpeg_proc.terminate()
                    self.ffmpeg_proc.wait()
            
        self.video_label.setText("Processing...")
        self.video_label.setPixmap(QPixmap())  # clear image
        
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        
        # Start background rendering
        self.render_thread = RenderThread(self.current_session)
        self.render_thread.finished_signal.connect(self.on_render_finished)
        self.render_thread.start()

    def on_render_finished(self, success):
        if success:
            self.status_label.setText("🟢 Processing complete! Play the video below.")
            self.status_label.setObjectName("statusReady")
            self.status_label.style().unpolish(self.status_label)
            self.status_label.style().polish(self.status_label)
            
            self.video_label.setVisible(False)
            self.video_widget.setVisible(True)
            self.play_btn.setVisible(True)
            
            final_video = self.current_session / "final_harmonized.mp4"
            self.media_player.setSource(QUrl.fromLocalFile(str(final_video.absolute())))
            self.media_player.play()
            self.play_btn.setText("⏸ Pause Video")
        else:
            self.status_label.setText("🔴 Error during processing.")
            self.status_label.setObjectName("statusRecording")
            self.status_label.style().unpolish(self.status_label)
            self.status_label.style().polish(self.status_label)
            self.video_label.setText("Processing Failed")
            
        self.start_btn.setEnabled(True)

    def cancel_recording(self):
        self.status_label.setText("🔴 Recording canceled.")
        self.status_label.setObjectName("statusRecording")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        if self.camera_thread:
            self.camera_thread.stop()
            self.camera_thread.wait()
            self.camera_thread = None
            
        if hasattr(self, 'ffmpeg_proc') and self.ffmpeg_proc:
            if self.ffmpeg_proc.poll() is None:
                try:
                    if self.ffmpeg_proc.stdin:
                        self.ffmpeg_proc.stdin.write(b'q\n')
                        self.ffmpeg_proc.stdin.flush()
                    
                    def drain():
                        self.ffmpeg_proc.stdout.read()
                    threading.Thread(target=drain, daemon=True).start()
                    
                    self.ffmpeg_proc.wait(timeout=5)
                except Exception:
                    self.ffmpeg_proc.terminate()
                    self.ffmpeg_proc.wait()
            
        self.video_label.setText("Preview will appear here")
        self.video_label.setPixmap(QPixmap())
        
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)

    def update_preview(self, pixmap: QPixmap):
        """Display the latest pre-scaled frame from CameraThread.

        Frame-drop strategy: if a frame is already pending display we skip the
        incoming one.  This prevents the Qt event queue from filling up with
        stale frames during a busy UI, which would cause cascading latency.
        """
        # Always paint — _display_pending guards against queue flood
        self._display_pending = False
        self.video_label.setPixmap(pixmap)


# ---------------------------------------------------------------------------
# CameraThread — pipelined producer/consumer with gesture throttling
# ---------------------------------------------------------------------------

class CameraThread(QThread):
    """Pipelined camera processing thread.

    Architecture
    ------------
    A single OS thread drives the full pipeline:

        decode_mjpeg_frames()  →  gesture inference (throttled to GESTURE_HZ)
                               →  HUD overlay render
                               →  AVI writer
                               →  Qt signal → UI

    The key latency improvements over the original monolithic approach are:

    1. **Gesture throttling**: MediaPipe runs at most ``GESTURE_HZ`` times per
       second (default 15 Hz).  Frames in between reuse the last detected
       degree — the HUD still updates every frame for smooth animation.

    2. **Frame-drop display**: The QImage is pre-scaled on this thread (not the
       Qt GUI thread) and we only emit when the previous frame has been
       consumed (``_display_pending`` flag on the window).  If the Qt thread
       is busy we skip rather than queue.

    3. **Pre-scaled QImage**: ``QPixmap.scaled()`` was previously called on
       every frame on the Qt GUI thread.  Now we scale the numpy array here
       using fast cv2.resize (bilinear) before building the QImage, then emit
       a ``QPixmap`` directly.
    """

    # Emits a pre-scaled QPixmap ready to set on the label (no scaling needed on UI thread)
    frame_ready = pyqtSignal(QPixmap)

    # Maximum gesture inference rate (Hz).  Raise if CPU allows.
    GESTURE_HZ = 15

    def __init__(self, mjpeg_stream, session_path, mappings):
        super().__init__()
        self.mjpeg_stream = mjpeg_stream
        self.session_path = session_path
        self.mappings = mappings
        self.running = False
        self.recognizer = GestureRecognizer()
        self.timeline = TimelineEngine(min_segment_s=0.0, stable_ms=0.0)

    def run(self):
        try:
            self.running = True
            frame_index = 0

            video_writer = None
            decorated_path = self.session_path / "decorated.avi"

            hud = None
            start_time = time.monotonic()

            # Gesture throttle state
            gesture_interval = 1.0 / self.GESTURE_HZ
            last_gesture_t = 0.0
            last_degree = "ONE"

            print("Starting camera thread reading from FFmpeg MJPEG stream (optimised pipeline)…")

            for frame, eof in decode_mjpeg_frames(self.mjpeg_stream):
                if not self.running or eof:
                    break

                now = time.monotonic()
                elapsed = now - start_time

                # ----------------------------------------------------------
                # Gesture inference — throttled to GESTURE_HZ
                # ----------------------------------------------------------
                if now - last_gesture_t >= gesture_interval:
                    # draw_skeleton=False: we draw the skeleton in _paint pass below
                    last_degree = self.recognizer.detect(frame, draw_skeleton=False)
                    last_gesture_t = now

                # Always draw the cached skeleton (one-frame stale at most)
                self.recognizer.draw_skeleton_onto(frame)

                degree = last_degree
                ts = frame_index / 30.0
                self.timeline.update(degree, ts)
                frame_index += 1

                # ----------------------------------------------------------
                # HUD overlay
                # ----------------------------------------------------------
                if hud is None:
                    h, w, _ = frame.shape
                    hud = HUDRenderer(w, h)

                chord_label = self.mappings.get(degree, degree)
                has_hand = self.recognizer.has_hand
                frame = hud.render(frame, degree, chord_label, is_recording=True, elapsed_time=elapsed, has_hand=has_hand)

                # ----------------------------------------------------------
                # Write decorated AVI (sync I/O on this thread — acceptable
                # because VideoWriter is fast and we need to preserve frames)
                # ----------------------------------------------------------
                if video_writer is None:
                    h, w, _ = frame.shape
                    fourcc = cv2.VideoWriter_fourcc(*'XVID')
                    video_writer = cv2.VideoWriter(str(decorated_path), fourcc, 30.0, (w, h))

                video_writer.write(frame)

                # ----------------------------------------------------------
                # Emit display frame — pre-scale on this thread, drop if UI
                # thread is still busy with the previous frame.
                # ----------------------------------------------------------
                # Get the parent window's display size
                parent = self.parent()
                if parent is not None:
                    pw = parent
                    # Skip emit if UI thread hasn't consumed the last frame yet
                    if getattr(pw, '_display_pending', False):
                        continue  # Drop this frame — keeps preview real-time

                    pw._display_pending = True

                # Pre-scale to the label display area on this thread
                h, w, _ = frame.shape
                target_w = PREVIEW_W
                target_h = int(h * target_w / w) if w > 0 else PREVIEW_H
                display_frame = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_LINEAR)

                rgb_image = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
                dh, dw, ch = rgb_image.shape
                bytes_per_line = ch * dw
                q_img = QImage(rgb_image.data, dw, dh, bytes_per_line, QImage.Format.Format_RGB888)
                # Build QPixmap here so Qt UI thread does zero image work
                pixmap = QPixmap.fromImage(q_img.copy())
                self.frame_ready.emit(pixmap)

            # ----------------------------------------------------------
            # Cleanup
            # ----------------------------------------------------------
            if video_writer:
                video_writer.release()

            end_ts = frame_index / 30.0
            self.timeline.write(self.session_path / "timeline.json", end_ts, pretty=True, force=True)
            self.recognizer.close()
            print("Camera thread stopped cleanly.")
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"CameraThread Exception: {e}")

    def stop(self):
        self.running = False


# ---------------------------------------------------------------------------
# RenderThread — unchanged logic, minor cleanup
# ---------------------------------------------------------------------------

class RenderThread(QThread):
    finished_signal = pyqtSignal(bool)
    
    def __init__(self, session_path):
        super().__init__()
        self.session_path = session_path
        
    def run(self):
        try:
            # First extract audio from the recorded video using ffmpeg
            video_file = self.session_path / "video.mp4"
            audio_file = self.session_path / "output.wav"
            if video_file.exists():
                subprocess.run([
                    "ffmpeg", "-y", "-i", str(video_file), 
                    "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2", str(audio_file)
                ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            import sys
            # Add core to sys.path if missing so vst_renderer can import properly
            if str(Path("core").resolve()) not in sys.path:
                sys.path.insert(0, str(Path("core").resolve()))
            
            render_vst([str(self.session_path)])
            
            final_video = self.session_path / "final_harmonized.mp4"
            harmonized_audio = self.session_path / "harmonized.wav"
            decorated_video = self.session_path / "decorated.avi"
            
            src_video = decorated_video if decorated_video.exists() else video_file
            
            if harmonized_audio.exists() and src_video.exists():
                subprocess.run([
                    "ffmpeg", "-y", "-i", str(src_video), "-i", str(harmonized_audio),
                    "-c:v", "libx264", "-preset", "fast", "-crf", "22", "-c:a", "aac", 
                    "-map", "0:v:0", "-map", "1:a:0",
                    str(final_video)
                ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
            self.finished_signal.emit(True)
        except Exception as e:
            print(f"Render failed: {e}")
            self.finished_signal.emit(False)
