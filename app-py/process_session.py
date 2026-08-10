import argparse
import json
import sys
import subprocess
from pathlib import Path
import cv2
import numpy as np
import math

# Ensure core and app-py are in sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(SCRIPT_DIR / "core") not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR / "core"))

from core.gesture.recognizer import GestureRecognizer
from core.timeline.engine import TimelineEngine
from core.engine.vst_renderer import render_session
from ui.hud import HUDRenderer

_SINE_TABLE_SIZE = 1024
_SINE_TABLE = np.sin(np.linspace(0, 2 * math.pi, _SINE_TABLE_SIZE, endpoint=False))

class CustomHUDRenderer(HUDRenderer):
    def __init__(self, width: int, height: int):
        # Calculate dynamic scale factor first since parent init calls _prerender_static_ui which depends on self.scale
        self.scale = (width / 960.0) * 0.95
        super().__init__(width, height)
        
        # Load scaled fonts
        self.font_large = self._load_font(int(64 * self.scale), bold=True)
        self.font_medium = self._load_font(int(24 * self.scale))
        self.font_small = self._load_font(int(14 * self.scale))
        self.font_title = self._load_font(int(20 * self.scale), bold=True)
        
        # Re-run static UI prerendering and dynamic panels initialization with correct fonts and scale
        self._prerender_static_ui()
        self._init_dynamic_panels()
        
        # BGR Light Lilac tint mask
        self.lilac_mask = np.full((height, width, 3), (255, 230, 240), dtype=np.uint8)

    def _prerender_static_ui(self):
        from PIL import Image, ImageDraw
        img = Image.new('RGBA', (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Scale coordinates
        sc = self.scale

        # Logo (Top Left)
        draw.text((int(32 * sc), int(32 * sc)), "GESTURE HARMONY", font=self.font_title, fill=self.color_white)

        # Chord Card (Left Middle) - modified width and height (made larger and scaled)
        card_x, card_y = int(32 * sc), int(120 * sc)
        card_w, card_h = int(270 * sc), int(210 * sc)
        self.chord_card_rect = (card_x, card_y, card_x + card_w, card_y + card_h)
        draw.rounded_rectangle(self.chord_card_rect, radius=int(18 * sc), fill=self.color_bg, outline=(255, 255, 255, 25), width=1)
        
        # Change label text to "Detected Harmony" and color to dark charcoal/slate
        draw.text((card_x + int(20 * sc), card_y + int(20 * sc)), "Detected Harmony", font=self.font_small, fill=(30, 41, 59, 255))

        # Status Bar Card (Bottom Left) - increased dimensions by 5% and scaled
        status_x = int(32 * sc)
        status_w = int(380 * sc)
        status_h = int(45 * sc)
        status_y = self.height - status_h - int(32 * sc)
        self.status_rect = (status_x, status_y, status_x + status_w, status_y + status_h)
        draw.rounded_rectangle(self.status_rect, radius=int(20 * sc), fill=self.color_bg, outline=(255, 255, 255, 25), width=1)

        # Record indicator bg (Top Right)
        rec_w, rec_h = int(160 * sc), int(40 * sc)
        rec_x, rec_y = self.width - rec_w - int(32 * sc), int(32 * sc)
        self.rec_rect = (rec_x, rec_y, rec_x + rec_w, rec_y + rec_h)
        draw.rounded_rectangle(self.rec_rect, radius=int(20 * sc), fill=self.color_bg, outline=(255, 255, 255, 25), width=1)

        # Pre-multiply alpha for extremely fast uint16 integer blending
        overlay_np = np.array(img)
        overlay_bgr = cv2.cvtColor(overlay_np[:, :, :3], cv2.COLOR_RGB2BGR)
        alpha = (overlay_np[:, :, 3] / 255.0 * 256).astype(np.uint16)
        alpha_3d = np.dstack([alpha] * 3)

        # Precalculate the static pre-multiplied color
        self.static_bgr_pre = (overlay_bgr.astype(np.uint16) * alpha_3d)
        self.static_inv_alpha = 256 - alpha_3d

    def render(self, frame, degree: str, chord_label: str, is_recording: bool, elapsed_time: float, has_hand: bool):
        import time
        t = time.time()
        self._frame_idx = (self._frame_idx + 1) % _SINE_TABLE_SIZE

        # Apply very light lilac filter (gives a nice life)
        frame = cv2.addWeighted(frame, 0.96, self.lilac_mask, 0.04, 0)

        # Apply Contrast & Fast Integer Vignette
        frame = cv2.convertScaleAbs(frame, alpha=1.02, beta=5)
        frame_16 = frame.astype(np.uint16)
        frame = ((frame_16 * self.vignette_mask_16) >> 8).astype(np.uint8)

        # Fast Integer Static Alpha Composite
        frame_16 = frame.astype(np.uint16)
        frame = ((self.static_bgr_pre + frame_16 * self.static_inv_alpha) >> 8).astype(np.uint8)

        # Dynamic Localized Overlay — Chord Card
        if degree != self.last_chord:
            self.last_chord = degree
            self.chord_change_time = t

        time_since_change = t - self.chord_change_time
        chord_scale = min(1.0, time_since_change / 0.2)

        card_x, card_y, card_x2, card_y2 = self.chord_card_rect
        card_w = card_x2 - card_x
        card_h = card_y2 - card_y

        self._chord_draw.rectangle([(0, 0), (card_w, card_h)], fill=(0, 0, 0, 0))

        alpha_val = int(255 * chord_scale)
        # Dark Violet color for the chords
        chord_color = (76, 29, 149, alpha_val)
        
        # Mapping TWO_MINOR to "2" instead of "2m"
        display_deg = {"ONE": "1", "TWO_MINOR": "2", "THREE_MINOR": "3m", "FOUR": "4"}.get(degree, degree)

        sc = self.scale
        self._chord_draw.text((int(20 * sc), int(45 * sc)), display_deg, font=self.font_large, fill=chord_color)
        self._chord_draw.text((int(20 * sc), int(135 * sc)), chord_label, font=self.font_medium, fill=self.color_white)

        # Waveform lookup
        wave_base_y = int(185 * sc)
        num_bars = 40
        bar_w = max(1, int(3 * sc))
        bar_gap = max(1, int(2 * sc))
        fi = self._frame_idx
        for i in range(num_bars):
            idx1 = int(fi * 5 + i * 10) % _SINE_TABLE_SIZE
            idx2 = int(fi * 2 - i * 3) % _SINE_TABLE_SIZE
            offset = _SINE_TABLE[idx1] * _SINE_TABLE[idx2]
            h_bar = max(2, int(15 * abs(offset) * sc))
            x = int(20 * sc) + i * (bar_w + bar_gap)
            self._chord_draw.rectangle([x, wave_base_y - h_bar, x + bar_w, wave_base_y + h_bar], fill=self.color_indigo)

        frame[card_y:card_y2, card_x:card_x2] = self._blend_roi(frame[card_y:card_y2, card_x:card_x2], self._chord_img, 'chord')

        # Dynamic Localized Overlay — Status Bar
        status_x, status_y, status_x2, status_y2 = self.status_rect
        status_w = status_x2 - status_x
        status_h = status_y2 - status_y

        self._status_draw.rectangle([(0, 0), (status_w, status_h)], fill=(0, 0, 0, 0))

        pulse_raw = (_SINE_TABLE[(fi * 6) % _SINE_TABLE_SIZE] + 1) / 2

        # Scale elements inside the status bar
        dot_size = max(4, int(10 * sc))
        
        # Get font height to center text
        try:
            bbox = self._status_draw.textbbox((0, 0), "Tracking", font=self.font_small)
            font_small_h = bbox[3] - bbox[1]
        except Exception:
            font_small_h = int(14 * sc)

        def draw_status(x, label, active, color):
            dot_alpha = int(150 + 105 * pulse_raw) if active else 100
            dot_color = color[:3] + (dot_alpha,) if active else self.color_gray
            dot_y1 = (status_h - dot_size) // 2
            dot_y2 = dot_y1 + dot_size
            self._status_draw.ellipse([x, dot_y1, x + dot_size, dot_y2], fill=dot_color)
            
            text_y = (status_h - font_small_h) // 2
            self._status_draw.text((x + dot_size + int(8 * sc), text_y), label, font=self.font_small, fill=self.color_white if active else self.color_gray)
            return x + int(115 * sc)

        sx = int(20 * sc)
        sx = draw_status(sx, "Tracking", True, self.color_accent)
        sx = draw_status(sx, "Listening", True, self.color_indigo)
        draw_status(sx, "Hand Detected", has_hand, self.color_white)

        frame[status_y:status_y2, status_x:status_x2] = self._blend_roi(frame[status_y:status_y2, status_x:status_x2], self._status_img, 'status')

        # Dynamic Localized Overlay — Record Indicator
        rec_x, rec_y, rec_right, rec_bottom = self.rec_rect
        rec_w = rec_right - rec_x
        rec_h = rec_bottom - rec_y

        self._rec_draw.rectangle([(0, 0), (rec_w, rec_h)], fill=(0, 0, 0, 0))

        m_val, s_val = divmod(int(elapsed_time), 60)
        h_val, m_val = divmod(m_val, 60)
        time_str = f"{h_val:02d}:{m_val:02d}:{s_val:02d}"

        bbox = self._rec_draw.textbbox((0, 0), time_str, font=self.font_medium)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        dot_size = max(4, int(10 * sc))
        gap = int(8 * sc)
        group_w = dot_size + gap + text_w

        start_x = (rec_w - group_w) / 2
        dot_x = start_x
        dot_y = (rec_h - dot_size) / 2 - 1
        text_x = dot_x + dot_size + gap
        text_y = (rec_h - text_h) / 2

        if is_recording:
            pulse_rec = (_SINE_TABLE[(fi * 4) % _SINE_TABLE_SIZE] + 1) / 2
            alpha_rec = int(215 + 25 * pulse_rec)
            self._rec_draw.ellipse((dot_x, dot_y, dot_x + dot_size, dot_y + dot_size), fill=(239, 68, 68, alpha_rec))
        else:
            self._rec_draw.ellipse((dot_x, dot_y, dot_x + dot_size, dot_y + dot_size), fill=(120, 120, 120))

        self._rec_draw.text((text_x, text_y), time_str, font=self.font_medium, fill=self.color_white)

        frame[rec_y:rec_bottom, rec_x:rec_right] = self._blend_roi(frame[rec_y:rec_bottom, rec_x:rec_right], self._rec_img, 'rec')

        return frame

def process_offline(session_path: Path):
    import math
    import numpy as np
    session_path = Path(session_path)
    video_file = session_path / "video.mp4"
    decorated_path = session_path / "decorated.avi"
    timeline_path = session_path / "timeline.json"
    pref_path = session_path / "chord_preferences.json"

    if not video_file.exists():
        raise FileNotFoundError(f"Missing video.mp4 in session: {video_file}")

    print(f"--> Loading chord preferences from {pref_path.name}...")
    mappings = {}
    if pref_path.exists():
        try:
            with pref_path.open("r", encoding="utf-8") as f:
                prefs = json.load(f)
            if prefs.get("mode") == "manual":
                raw_mappings = prefs.get("mappings") or {}
                for k, v in raw_mappings.items():
                    key = k
                    if k == "TWO":
                        key = "TWO_MINOR"
                    elif k == "THREE":
                        key = "THREE_MINOR"
                    mappings[key] = v.get("label", k)
        except Exception as e:
            print(f"Warning: Could not load chord preferences: {e}")

    if not mappings:
        mappings = {"ONE": "C Major", "TWO_MINOR": "D Minor", "THREE_MINOR": "E Minor", "FOUR": "F Major"}

    print("--> Initializing Gesture Recognizer and HUD Renderer...")
    recognizer = GestureRecognizer()
    timeline = TimelineEngine(min_segment_s=0.0, stable_ms=0.0)

    cap = cv2.VideoCapture(str(video_file))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    print(f"--> Processing video: {width}x{height} @ {fps} fps ({total_frames} frames)...")
    hud = CustomHUDRenderer(width, height)

    fourcc = cv2.VideoWriter_fourcc(*'XVID')
    video_writer = cv2.VideoWriter(str(decorated_path), fourcc, fps, (width, height))

    frame_index = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Process gestures and draw hand skeleton
        degree = recognizer.detect(frame, draw_skeleton=True)
        ts = frame_index / fps
        timeline.update(degree, ts)
        frame_index += 1

        # Render HUD overlay on the frame
        chord_label = mappings.get(degree, degree)
        has_hand = recognizer.has_hand
        frame = hud.render(frame, degree, chord_label, is_recording=True, elapsed_time=ts, has_hand=has_hand)

        video_writer.write(frame)

        if frame_index % 100 == 0 or frame_index == total_frames:
            print(f"    Progress: {frame_index}/{total_frames} frames processed...")

    cap.release()
    video_writer.release()
    recognizer.close()

    # Write timeline.json
    end_ts = frame_index / fps
    timeline.write(timeline_path, end_ts, pretty=True, force=True)
    print(f"--> Saved timeline to {timeline_path}")

    # Extract audio if output.wav is missing
    audio_file = session_path / "output.wav"
    if not audio_file.exists():
        print(f"--> Extracting audio from video.mp4 to {audio_file.name}...")
        subprocess.run([
            "ffmpeg", "-y", "-i", str(video_file),
            "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2", str(audio_file)
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Render harmonized audio via REAPER VST
    harmonized_audio = session_path / "harmonized.wav"
    if not harmonized_audio.exists():
        print("--> Rendering harmonized vocal via VST...")
        render_session(session_path)

    # Merge annotated video and harmonized audio using high quality H.264
    final_video = session_path / "final_harmonized.mp4"
    print(f"--> Merging annotated video and harmonized audio to {final_video.name}...")
    subprocess.run([
        "ffmpeg", "-y", "-i", str(decorated_path), "-i", str(harmonized_audio),
        "-c:v", "libx264", "-preset", "fast", "-crf", "21", "-c:a", "aac",
        "-map", "0:v:0", "-map", "1:a:0",
        str(final_video)
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Clean up intermediate decorated.avi to save space
    if decorated_path.exists():
        decorated_path.unlink()

    print(f"🎉 Offline processing complete! Output saved to: {final_video}")

def main():
    parser = argparse.ArgumentParser(description="Offline Gesture Harmony processing tool")
    parser.add_argument("session_path", help="Path to the session folder")
    args = parser.parse_args()

    session_dir = Path(args.session_path)
    if not session_dir.exists():
        print(f"Error: Session directory {session_dir} does not exist.")
        return 1

    try:
        process_offline(session_dir)
        return 0
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
