from __future__ import annotations

import math
import numpy as np


def constant_power_pan(audio: np.ndarray, pan: float) -> tuple[np.ndarray, np.ndarray]:
    pan = max(-1.0, min(1.0, pan))
    angle = (pan + 1.0) * (math.pi / 4.0)
    return audio * math.cos(angle), audio * math.sin(angle)


def safe_normalize(stereo: np.ndarray, target_peak: float = 0.95) -> np.ndarray:
    peak = float(np.max(np.abs(stereo))) if stereo.size else 0.0
    if peak <= 0:
        return stereo
    if peak > target_peak:
        stereo = (stereo / peak) * target_peak
    return stereo
