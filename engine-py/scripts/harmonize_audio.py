from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

SCRIPT_DIR = Path(__file__).resolve().parent
ENGINE_ROOT = SCRIPT_DIR.parent
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

from audio.mixing import constant_power_pan, safe_normalize
from audio.pitch import estimate_pitch_contour
from harmony.arranger import build_voice_targets, hz_to_midi
from harmony.music_theory import MusicContext, chord_pitch_classes
from utils.logging_utils import configure_logging

log = configure_logging("harmonize")


def load_json(path: Path):
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def choose_harmony_intervals(voice_idx: int, target_midi: float, melody_midi: float) -> tuple[float, float]:
    steps = target_midi - melody_midi
    if voice_idx == 0:
        pan = 0.0
        gain = 0.75
    elif voice_idx in (1, 2):
        pan = -0.4 if voice_idx == 1 else 0.4
        gain = 0.6
    else:
        pan = 0.8
        gain = 0.5
    return steps, pan * np.sign(steps if steps != 0 else 1), gain


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python harmonize_audio.py <session_path>")
        return 2

    session = Path(sys.argv[1])
    input_wav = session / "output.wav"
    timeline_path = session / "timeline.json"
    config_path = session / "config.json"
    out_path = session / "harmonized_enhanced.wav"

    timeline = load_json(timeline_path)
    config = load_json(config_path)

    if not input_wav.exists():
        raise FileNotFoundError(input_wav)

    y, sr = librosa.load(str(input_wav), sr=None, mono=True)
    if y.ndim != 1:
        y = librosa.to_mono(y)

    f0, f0_times = estimate_pitch_contour(y, sr, hop=512)

    ctx = MusicContext(key=str(config.get("key", "C")), scale=str(config.get("scale", "major")))
    mix = float(config.get("mix", 0.5))
    voices = max(1, min(4, int(float(config.get("voices", 4)))))

    out_l = np.zeros_like(y)
    out_r = np.zeros_like(y)

    dry_l, dry_r = constant_power_pan(y, 0.0)
    out_l += dry_l * 0.8
    out_r += dry_r * 0.8

    shift_cache: dict[tuple[int, int], np.ndarray] = {}

    for seg in timeline:
        start = float(seg.get("start", 0.0))
        end = float(seg.get("end", 0.0))
        degree = str(seg.get("degree", "I")).upper()
        if end <= start:
            continue

        s0 = max(0, int(round(start * sr)))
        s1 = min(len(y), int(round(end * sr)))
        if s1 <= s0:
            continue

        mask = (f0_times >= start) & (f0_times < end)
        seg_f0 = f0[mask]
        seg_f0 = seg_f0[np.isfinite(seg_f0)]
        if seg_f0.size == 0:
            continue

        melody_midi = float(np.median([hz_to_midi(v) for v in seg_f0]))
        pcs = chord_pitch_classes(ctx, degree)
        voice_targets = build_voice_targets(melody_midi, pcs, voices=voices)

        seg_audio = y[s0:s1]

        for idx, target in enumerate(voice_targets):
            steps, pan, gain = choose_harmony_intervals(idx, target, melody_midi)
            if abs(steps) < 0.2:
                continue

            key = (len(seg_audio), int(round(steps * 100)))
            shifted = shift_cache.get(key)
            if shifted is None:
                shifted = librosa.effects.pitch_shift(seg_audio, sr=sr, n_steps=steps, bins_per_octave=24)
                shift_cache[key] = shifted

            v_l, v_r = constant_power_pan(shifted, float(pan))

            seg_len = s1 - s0
            mix_len = min(seg_len, len(v_l), len(v_r))
            if mix_len <= 0:
                continue

            out_l[s0:s0 + mix_len] += v_l[:mix_len] * mix * gain
            out_r[s0:s0 + mix_len] += v_r[:mix_len] * mix * gain

    stereo = np.vstack((out_l, out_r)).T
    stereo = safe_normalize(stereo, target_peak=0.95)
    sf.write(str(out_path), stereo, sr)

    log.info("Harmonized audio exported: %s", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
