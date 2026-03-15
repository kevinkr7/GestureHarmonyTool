from __future__ import annotations

import numpy as np
import librosa


def estimate_pitch_contour(audio: np.ndarray, sr: int, hop: int = 512) -> tuple[np.ndarray, np.ndarray]:
    f0, _, _ = librosa.pyin(audio, fmin=65, fmax=1046, sr=sr, hop_length=hop)

    if f0 is None or not np.isfinite(f0).any():
        f0 = librosa.yin(audio, fmin=65, fmax=1046, sr=sr, frame_length=2048, hop_length=hop)

    if f0 is None or not np.isfinite(f0).any():
        stft = np.abs(librosa.stft(audio, n_fft=2048, hop_length=hop))
        idx = np.argmax(stft, axis=0)
        freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
        f0 = freqs[idx]

    f0 = np.where(np.isfinite(f0), f0, np.nan)

    # median smoothing
    pad = 2
    smoothed = np.copy(f0)
    for i in range(len(f0)):
        lo = max(0, i - pad)
        hi = min(len(f0), i + pad + 1)
        vals = f0[lo:hi]
        vals = vals[np.isfinite(vals)]
        if vals.size:
            smoothed[i] = float(np.median(vals))

    times = librosa.frames_to_time(np.arange(len(smoothed)), sr=sr, hop_length=hop)
    return smoothed, times
