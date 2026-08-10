import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import time
import math
import os

# Pre-computed sine table for the waveform animation — avoids math.sin() calls
# in the hot render loop.  1024 steps wrap at any frame rate.
_SINE_TABLE_SIZE = 1024
_SINE_TABLE = np.sin(np.linspace(0, 2 * math.pi, _SINE_TABLE_SIZE, endpoint=False))


class HUDRenderer:
    """Renders a cinematic HUD overlay onto live camera frames.

    Performance improvements over the original implementation
    ---------------------------------------------------------
    * Static UI layer (logo, card backgrounds, record bg) is pre-composited
      once at ``__init__`` time as pre-multiplied uint16 arrays, then blended
      each frame with a single NumPy vectorised operation — no Python loop.
    * The three dynamic panels (chord card, status bar, record indicator) each
      have a *persistent* ``PIL.Image`` + ``ImageDraw`` object that is reused
      every frame.  Before painting, the image is cleared to transparent black
      with ``ImageDraw.rectangle`` on the full region rather than creating a
      new ``Image`` object on every call.
    * Waveform sin values are looked up from a pre-computed NumPy table instead
      of calling ``math.sin()`` 40× per frame.
    * The ``_blend_roi`` helper caches its intermediate uint16 arrays across
      calls for each of the three fixed-size panels to avoid repeated
      ``np.empty`` allocations.
    """

    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height

        # Colors (Deep Violet, Electric Purple, Soft Indigo, Cool White, Muted Gray)
        self.color_bg = (15, 17, 23, 89)         # 35% opacity dark
        self.color_accent = (147, 51, 234, 255)  # Electric Purple
        self.color_indigo = (99, 102, 241, 255)  # Soft Indigo
        self.color_white = (248, 250, 252, 255)
        self.color_gray = (148, 163, 184, 255)

        self.font_large = self._load_font(64, bold=True)
        self.font_medium = self._load_font(24)
        self.font_small = self._load_font(14)
        self.font_title = self._load_font(20, bold=True)

        self._init_vignette()
        self._prerender_static_ui()
        self._init_dynamic_panels()

        self.last_chord = ""
        self.chord_change_time = 0.0

        # Frame counter for sine table lookup (wraps at _SINE_TABLE_SIZE)
        self._frame_idx: int = 0

    # ------------------------------------------------------------------
    # Initialisation helpers
    # ------------------------------------------------------------------

    def _load_font(self, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        fonts_to_try = [
            "C:/Windows/Fonts/seguisb.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"
        ]
        for f in fonts_to_try:
            if os.path.exists(f):
                return ImageFont.truetype(f, size)
        return ImageFont.load_default()

    def _init_vignette(self):
        X = cv2.getGaussianKernel(self.width, self.width / 1.5)
        Y = cv2.getGaussianKernel(self.height, self.height / 1.5)
        kernel = Y * X.T
        mask = kernel / kernel.max()
        vignette_mask = (mask * 0.4 + 0.6) * 256.0
        self.vignette_mask_16 = np.dstack([vignette_mask] * 3).astype(np.uint16)

    def _prerender_static_ui(self):
        img = Image.new('RGBA', (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Logo (Top Left)
        draw.text((32, 32), "GESTURE HARMONY", font=self.font_title, fill=self.color_white)

        # Chord Card (Left Middle)
        card_x, card_y = 32, 120
        card_w, card_h = 240, 180
        self.chord_card_rect = (card_x, card_y, card_x + card_w, card_y + card_h)
        draw.rounded_rectangle(self.chord_card_rect, radius=18, fill=self.color_bg, outline=(255, 255, 255, 25), width=1)
        draw.text((card_x + 20, card_y + 20), "DETECTED CHORD", font=self.font_small, fill=self.color_gray)

        # Status Bar Card (Bottom Left)
        status_x, status_y = 32, self.height - 70
        status_w, status_h = 370, 40
        self.status_rect = (status_x, status_y, status_x + status_w, status_y + status_h)
        draw.rounded_rectangle(self.status_rect, radius=20, fill=self.color_bg, outline=(255, 255, 255, 25), width=1)

        # Record indicator bg (Top Right)
        rec_w, rec_h = 160, 40
        rec_x, rec_y = self.width - rec_w - 32, 32
        self.rec_rect = (rec_x, rec_y, rec_x + rec_w, rec_y + rec_h)
        draw.rounded_rectangle(self.rec_rect, radius=20, fill=self.color_bg, outline=(255, 255, 255, 25), width=1)

        # Pre-multiply alpha for extremely fast uint16 integer blending
        overlay_np = np.array(img)
        overlay_bgr = cv2.cvtColor(overlay_np[:, :, :3], cv2.COLOR_RGB2BGR)
        alpha = (overlay_np[:, :, 3] / 255.0 * 256).astype(np.uint16)
        alpha_3d = np.dstack([alpha] * 3)

        # Precalculate the static pre-multiplied color (0 to 255 * 256)
        self.static_bgr_pre = (overlay_bgr.astype(np.uint16) * alpha_3d)
        self.static_inv_alpha = 256 - alpha_3d

    def _init_dynamic_panels(self):
        """Pre-allocate reusable PIL Image + ImageDraw for each dynamic panel.

        Instead of ``Image.new(...)`` every frame (which allocates heap memory
        and copies zeros), we keep one image per panel and clear it cheaply
        at the start of each render call.
        """
        card_x, card_y, card_x2, card_y2 = self.chord_card_rect
        self._chord_img = Image.new('RGBA', (card_x2 - card_x, card_y2 - card_y), (0, 0, 0, 0))
        self._chord_draw = ImageDraw.Draw(self._chord_img)

        sx, sy, sx2, sy2 = self.status_rect
        self._status_img = Image.new('RGBA', (sx2 - sx, sy2 - sy), (0, 0, 0, 0))
        self._status_draw = ImageDraw.Draw(self._status_img)

        rx, ry, rx2, ry2 = self.rec_rect
        self._rec_img = Image.new('RGBA', (rx2 - rx, ry2 - ry), (0, 0, 0, 0))
        self._rec_draw = ImageDraw.Draw(self._rec_img)

        # Per-panel blend scratch buffers (allocated once, reused every frame)
        self._blend_scratch: dict[str, np.ndarray] = {}

    # ------------------------------------------------------------------
    # Hot-path blending helper
    # ------------------------------------------------------------------

    def _blend_roi(self, frame_roi: np.ndarray, pil_img: Image.Image, key: str) -> np.ndarray:
        """Alpha-blend *pil_img* over *frame_roi* using pre-allocated scratch buffers.

        *key* identifies the panel ('chord', 'status', 'rec') so per-panel
        uint16 intermediates are allocated once and reused every frame.
        """
        img_np = np.array(pil_img)
        img_bgr = cv2.cvtColor(img_np[:, :, :3], cv2.COLOR_RGB2BGR)

        # Retrieve or create cached uint16 scratch arrays for this panel.
        if key not in self._blend_scratch:
            h, w = img_np.shape[:2]
            self._blend_scratch[key] = {
                'alpha_3d': np.empty((h, w, 3), dtype=np.uint16),
                'img_bgr_16': np.empty((h, w, 3), dtype=np.uint16),
            }
        cache = self._blend_scratch[key]

        # alpha in [0, 256] so we can use integer right-shift instead of divide
        alpha = (img_np[:, :, 3].astype(np.uint16) * 256) // 255
        # Broadcast alpha to all 3 channels into the pre-allocated buffer
        np.stack([alpha, alpha, alpha], axis=-1, out=cache['alpha_3d'])
        # Copy img_bgr into the pre-allocated uint16 buffer
        np.copyto(cache['img_bgr_16'], img_bgr)

        frame_roi_16 = frame_roi.astype(np.uint16)
        blended_16 = (cache['img_bgr_16'] * cache['alpha_3d']
                      + frame_roi_16 * (256 - cache['alpha_3d'])) >> 8
        return blended_16.astype(np.uint8)

    # ------------------------------------------------------------------
    # Main render entry point
    # ------------------------------------------------------------------

    def render(self, frame, degree: str, chord_label: str, is_recording: bool, elapsed_time: float, has_hand: bool):
        t = time.time()
        self._frame_idx = (self._frame_idx + 1) % _SINE_TABLE_SIZE

        # 1. Apply Contrast & Fast Integer Vignette
        frame = cv2.convertScaleAbs(frame, alpha=1.02, beta=5)
        frame_16 = frame.astype(np.uint16)
        frame = ((frame_16 * self.vignette_mask_16) >> 8).astype(np.uint8)

        # 2. Fast Integer Static Alpha Composite
        frame_16 = frame.astype(np.uint16)
        frame = ((self.static_bgr_pre + frame_16 * self.static_inv_alpha) >> 8).astype(np.uint8)

        # 3. Dynamic Localized Overlay — Chord Card
        if degree != self.last_chord:
            self.last_chord = degree
            self.chord_change_time = t

        time_since_change = t - self.chord_change_time
        chord_scale = min(1.0, time_since_change / 0.2)

        card_x, card_y, card_x2, card_y2 = self.chord_card_rect
        card_w = card_x2 - card_x
        card_h = card_y2 - card_y

        # Clear the reused image by drawing a transparent rectangle
        self._chord_draw.rectangle([(0, 0), (card_w, card_h)], fill=(0, 0, 0, 0))

        alpha_val = int(255 * chord_scale)
        chord_color = self.color_accent[:3] + (alpha_val,)
        display_deg = {"ONE": "1", "TWO_MINOR": "2m", "THREE_MINOR": "3m", "FOUR": "4"}.get(degree, degree)

        self._chord_draw.text((20, 40), display_deg, font=self.font_large, fill=chord_color)
        self._chord_draw.text((20, 120), chord_label, font=self.font_medium, fill=self.color_white)

        # Waveform — look up pre-computed sine values instead of calling math.sin() 40×
        wave_base_y = 160
        num_bars = 40
        bar_w = 3
        bar_gap = 2
        fi = self._frame_idx
        for i in range(num_bars):
            # Two-frequency product — use table lookup with integer index arithmetic
            idx1 = int(fi * 5 + i * 10) % _SINE_TABLE_SIZE  # ~t*5 + i*0.3 scaled to table
            idx2 = int(fi * 2 - i * 3) % _SINE_TABLE_SIZE   # ~t*2 - i*0.1 scaled
            offset = _SINE_TABLE[idx1] * _SINE_TABLE[idx2]
            h_bar = max(2, int(12 * abs(offset)))
            x = 20 + i * (bar_w + bar_gap)
            self._chord_draw.rectangle([x, wave_base_y - h_bar, x + bar_w, wave_base_y + h_bar], fill=self.color_indigo)

        frame[card_y:card_y2, card_x:card_x2] = self._blend_roi(frame[card_y:card_y2, card_x:card_x2], self._chord_img, 'chord')

        # 4. Dynamic Localized Overlay — Status Bar
        status_x, status_y, status_x2, status_y2 = self.status_rect
        status_w = status_x2 - status_x
        status_h = status_y2 - status_y

        self._status_draw.rectangle([(0, 0), (status_w, status_h)], fill=(0, 0, 0, 0))

        pulse_raw = (_SINE_TABLE[(fi * 6) % _SINE_TABLE_SIZE] + 1) / 2

        def draw_status(x, label, active, color):
            dot_alpha = int(150 + 105 * pulse_raw) if active else 100
            dot_color = color[:3] + (dot_alpha,) if active else self.color_gray
            self._status_draw.ellipse([x, 15, x + 10, 25], fill=dot_color)
            self._status_draw.text((x + 18, 10), label, font=self.font_small, fill=self.color_white if active else self.color_gray)
            return x + 110

        sx = 20
        sx = draw_status(sx, "Tracking", True, self.color_accent)
        sx = draw_status(sx, "Listening", True, self.color_indigo)
        draw_status(sx, "Hand Detected", has_hand, self.color_white)

        frame[status_y:status_y2, status_x:status_x2] = self._blend_roi(frame[status_y:status_y2, status_x:status_x2], self._status_img, 'status')

        # 5. Dynamic Localized Overlay — Record Indicator
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

        dot_size = 10
        gap = 8
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
