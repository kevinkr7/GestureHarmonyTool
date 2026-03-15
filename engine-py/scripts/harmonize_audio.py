from __future__ import annotations

import importlib
import importlib.util
import json
import random
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
from harmony.arranger import hz_to_midi
from harmony.music_theory import MusicContext, chord_pitch_classes, detect_music_context, scale_pitch_classes
from utils.logging_utils import configure_logging

log = configure_logging("harmonize")


def load_json(path: Path):
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def optional_module(name: str):
    if importlib.util.find_spec(name) is None:
        return None
    return importlib.import_module(name)


def nearest_scale_midi(midi_value: float, scale_pcs: list[int]) -> float:
    candidates = []
    base_oct = int(np.floor(midi_value / 12.0))
    for octv in range(base_oct - 1, base_oct + 2):
        for pc in scale_pcs:
            candidates.append(octv * 12 + pc)
    return min(candidates, key=lambda v: abs(v - midi_value)) if candidates else midi_value


def make_voice_targets(melody_midi: float, chord_pcs: list[int], voices: int) -> list[float]:
    root = chord_pcs[0]
    third = chord_pcs[1 % len(chord_pcs)]
    fifth = chord_pcs[2 % len(chord_pcs)]

    base_oct = int(melody_midi // 12) * 12
    raw_targets = [
        melody_midi,
        base_oct + third,
        base_oct + fifth,
        melody_midi + 12,
    ]

    bounded: list[float] = []
    min_gap = 3.0
    for idx, target in enumerate(raw_targets[: max(1, min(voices, 4))]):
        if idx == 0:
            bounded.append(target)
            continue
        while target - bounded[-1] < min_gap:
            target += 12
        bounded.append(target)
    return bounded


def apply_fade_edges(audio: np.ndarray, sr: int, fade_ms: float = 30.0) -> np.ndarray:
    if audio.size == 0:
        return audio
    fade_len = int(sr * max(0.0, fade_ms) / 1000.0)
    fade_len = min(fade_len, len(audio) // 2)
    if fade_len <= 0:
        return audio
    env = np.ones(len(audio), dtype=np.float32)
    env[:fade_len] = np.linspace(0.0, 1.0, fade_len)
    env[-fade_len:] = np.linspace(1.0, 0.0, fade_len)
    return audio * env


def pitch_shift_with_world(audio: np.ndarray, sr: int, steps: float) -> np.ndarray:
    pyworld = optional_module("pyworld")
    if pyworld is None:
        return librosa.effects.pitch_shift(audio, sr=sr, n_steps=steps, bins_per_octave=24)

    x = audio.astype(np.float64)
    f0, t = pyworld.harvest(x, sr)
    sp = pyworld.cheaptrick(x, f0, t, sr)
    ap = pyworld.d4c(x, f0, t, sr)
    ratio = 2.0 ** (steps / 12.0)
    shifted_f0 = np.where(f0 > 0, f0 * ratio, f0)
    out = pyworld.synthesize(shifted_f0, sp, ap, sr)
    return out[: len(audio)].astype(np.float32)


def pitch_shift_natural(audio: np.ndarray, sr: int, steps: float, use_formant: bool = True) -> np.ndarray:
    pyrb = optional_module("pyrubberband")
    if pyrb is not None:
        rbargs = {"--formant": ""} if use_formant else None
        try:
            shifted = pyrb.pitch_shift(audio.astype(np.float32), sr, steps, rbargs=rbargs)
        except TypeError:
            shifted = pyrb.pitch_shift(audio.astype(np.float32), sr, steps)
        return shifted.astype(np.float32)

    return pitch_shift_with_world(audio, sr, steps)


def apply_chorus(audio: np.ndarray, sr: int, rate_hz: float = 0.2, depth_ms: float = 5.0, base_delay_ms: float = 20.0) -> np.ndarray:
    if audio.size == 0:
        return audio
    depth = int(sr * depth_ms / 1000.0)
    base = int(sr * base_delay_ms / 1000.0)
    if base <= 0:
        return audio

    out = np.copy(audio)
    n = np.arange(len(audio))
    lfo = (np.sin(2 * np.pi * rate_hz * (n / sr)) + 1.0) * 0.5
    delays = base + (lfo * depth).astype(int)

    for i in range(base + depth, len(audio)):
        out[i] += 0.35 * audio[i - delays[i]]
    return out


def convolve_reverb(stereo: np.ndarray, sr: int, wet: float = 0.18) -> np.ndarray:
    wet = max(0.0, min(0.5, wet))
    ir_path = ENGINE_ROOT / "assets" / "ir" / "studio_room.wav"

    if ir_path.exists():
        ir, ir_sr = librosa.load(str(ir_path), sr=sr, mono=False)
        if ir.ndim == 1:
            ir = np.vstack([ir, ir])
    else:
        ir_len = int(sr * 0.8)
        t = np.linspace(0.0, 1.0, ir_len, endpoint=False)
        decay = np.exp(-5.0 * t)
        left = decay * (0.8 + 0.2 * np.sin(2 * np.pi * 2.0 * t))
        right = decay * (0.8 + 0.2 * np.cos(2 * np.pi * 2.3 * t))
        ir = np.vstack([left, right]).astype(np.float32)

    scipy_signal = optional_module("scipy.signal")
    if scipy_signal is not None:
        rev_l = scipy_signal.fftconvolve(stereo[:, 0], ir[0], mode="full")[: len(stereo)]
        rev_r = scipy_signal.fftconvolve(stereo[:, 1], ir[1], mode="full")[: len(stereo)]
    else:
        rev_l = np.convolve(stereo[:, 0], ir[0], mode="full")[: len(stereo)]
        rev_r = np.convolve(stereo[:, 1], ir[1], mode="full")[: len(stereo)]

    reverbed = np.column_stack([rev_l, rev_r]).astype(np.float32)
    return stereo * (1.0 - wet) + reverbed * wet


def apply_eq_and_compression(stereo: np.ndarray, sr: int) -> np.ndarray:
    if stereo.size == 0:
        return stereo

    # High-pass around 80Hz
    hp_l = stereo[:, 0] - librosa.effects.preemphasis(stereo[:, 0], coef=0.97)
    hp_r = stereo[:, 1] - librosa.effects.preemphasis(stereo[:, 1], coef=0.97)
    processed = np.column_stack([hp_l, hp_r])

    # Presence boost around 4kHz (simple shelving approximation)
    boost = librosa.effects.preemphasis(processed[:, 0], coef=0.75) * 0.08
    processed[:, 0] += boost
    boost_r = librosa.effects.preemphasis(processed[:, 1], coef=0.75) * 0.08
    processed[:, 1] += boost_r

    # Compressor (2:1 above -18 dB)
    threshold = 10 ** (-18.0 / 20.0)
    ratio = 2.0
    for c in range(2):
        x = processed[:, c]
        mag = np.abs(x)
        over = mag > threshold
        compressed = np.copy(mag)
        compressed[over] = threshold + (mag[over] - threshold) / ratio
        processed[:, c] = np.sign(x) * compressed
    return processed


def normalize_lufs_approx(stereo: np.ndarray, target_lufs: float = -14.0) -> np.ndarray:
    if stereo.size == 0:
        return stereo
    mono = np.mean(stereo, axis=1)
    rms = float(np.sqrt(np.mean(np.square(mono)) + 1e-12))
    current_db = 20.0 * np.log10(max(rms, 1e-9))
    gain_db = target_lufs - current_db
    gain = 10.0 ** (gain_db / 20.0)
    return stereo * gain


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python harmonize_audio.py <session_path>")
        return 2

    session = Path(sys.argv[1])
    input_wav = session / "output.wav"
    timeline_path = session / "timeline.json"
    config_path = session / "config.json"
    out_path = session / "harmonized_enhanced.wav"
    mastered_out_path = session / "harmonized_mastered.wav"

    timeline = load_json(timeline_path)
    config = load_json(config_path)

    if not input_wav.exists():
        raise FileNotFoundError(input_wav)

    y, sr = librosa.load(str(input_wav), sr=None, mono=True)
    if y.ndim != 1:
        y = librosa.to_mono(y)

    f0, f0_times = estimate_pitch_contour(y, sr, hop=512)

    detected_ctx = detect_music_context(y, sr)
    ctx = MusicContext(key=detected_ctx.key, scale=detected_ctx.scale)
    config["detected_key"] = ctx.key
    config["detected_scale"] = ctx.scale
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    log.info("Detected musical context from audio: key=%s scale=%s", ctx.key, ctx.scale)

    mix = float(config.get("mix", 0.5))
    voices = max(1, min(4, int(float(config.get("voices", 4)))))
    scale_pcs = scale_pitch_classes(ctx)

    out_l = np.zeros_like(y)
    out_r = np.zeros_like(y)

    lead_gain = 0.7
    harmony_gain = 0.3
    dry_l, dry_r = constant_power_pan(y, 0.0)
    out_l += dry_l * lead_gain
    out_r += dry_r * lead_gain

    shift_cache: dict[tuple[int, int], np.ndarray] = {}

    for seg_idx, seg in enumerate(timeline):
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
        tuned_midi = nearest_scale_midi(melody_midi, scale_pcs)
        tune_shift = tuned_midi - melody_midi

        seg_audio_raw = y[s0:s1]
        if abs(tune_shift) >= 0.1:
            seg_audio = pitch_shift_natural(seg_audio_raw, sr, tune_shift, use_formant=True)
        else:
            seg_audio = seg_audio_raw

        seg_audio = apply_fade_edges(seg_audio, sr, fade_ms=30.0)
        chord_pcs = chord_pitch_classes(ctx, degree)
        voice_targets = make_voice_targets(tuned_midi, chord_pcs, voices=voices)

        for idx, target in enumerate(voice_targets):
            if idx == 0:
                continue

            rng = random.Random((seg_idx + 1) * 100 + idx)
            detune = rng.uniform(-0.05, 0.05)  # semitones (~+-5 cents)
            delay_samples = int(sr * rng.uniform(0.01, 0.03))

            steps = (target - tuned_midi) + detune
            if abs(steps) < 0.1:
                continue

            cache_key = (len(seg_audio), int(round(steps * 100)))
            shifted = shift_cache.get(cache_key)
            if shifted is None:
                shifted = pitch_shift_natural(seg_audio, sr, steps, use_formant=True)
                shift_cache[cache_key] = shifted

            shifted = apply_chorus(shifted, sr, rate_hz=0.2, depth_ms=5.0, base_delay_ms=20.0)
            if delay_samples > 0:
                shifted = np.pad(shifted, (delay_samples, 0))[: len(seg_audio)]

            if idx == 1:
                pan = -0.3
            elif idx == 2:
                pan = 0.3
            else:
                pan = 0.6

            v_l, v_r = constant_power_pan(shifted, pan)
            seg_len = s1 - s0
            mix_len = min(seg_len, len(v_l), len(v_r))
            if mix_len <= 0:
                continue

            per_voice_gain = harmony_gain / max(1, (len(voice_targets) - 1))
            out_l[s0:s0 + mix_len] += v_l[:mix_len] * mix * per_voice_gain
            out_r[s0:s0 + mix_len] += v_r[:mix_len] * mix * per_voice_gain

    stereo = np.vstack((out_l, out_r)).T
    stereo = convolve_reverb(stereo, sr, wet=0.18)
    stereo = safe_normalize(stereo, target_peak=0.95)
    sf.write(str(out_path), stereo, sr)

    mastered = apply_eq_and_compression(stereo, sr)
    mastered = normalize_lufs_approx(mastered, target_lufs=-14.0)
    mastered = safe_normalize(mastered, target_peak=0.98)
    sf.write(str(mastered_out_path), mastered, sr)

    log.info("Harmonized audio exported: %s", out_path)
    log.info("Mastered harmonized audio exported: %s", mastered_out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
