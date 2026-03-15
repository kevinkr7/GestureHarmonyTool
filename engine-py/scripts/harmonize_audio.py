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


def fallback_melody_midi(seg_audio: np.ndarray, sr: int) -> float:
    if seg_audio.size == 0:
        return 60.0
    stft = np.abs(librosa.stft(seg_audio, n_fft=2048, hop_length=512))
    if stft.size == 0:
        return 60.0
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    idx = int(np.argmax(np.mean(stft, axis=1)))
    hz = float(freqs[idx]) if 0 <= idx < len(freqs) else 261.63
    if hz <= 0:
        hz = 261.63
    return float(hz_to_midi(hz))


def make_voice_targets(melody_midi: float, chord_pcs: list[int], voices: int) -> list[float]:
    root = chord_pcs[0]
    third = chord_pcs[1 % len(chord_pcs)]
    fifth = chord_pcs[2 % len(chord_pcs)]

    base_oct = int(melody_midi // 12) * 12
    raw_targets = [melody_midi, base_oct + third, base_oct + fifth, melody_midi + 12]

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


def build_segment_envelope(length: int, sr: int, crossfade_ms: float = 30.0) -> np.ndarray:
    if length <= 0:
        return np.array([], dtype=np.float32)
    fade_len = int(sr * max(0.0, crossfade_ms) / 1000.0)
    fade_len = min(fade_len, length // 2)
    env = np.ones(length, dtype=np.float32)
    if fade_len > 0:
        env[:fade_len] = np.linspace(0.0, 1.0, fade_len)
        env[-fade_len:] = np.linspace(1.0, 0.0, fade_len)
    return env


def estimate_pitch_contour_with_crepe(audio: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray]:
    crepe = optional_module("crepe")
    if crepe is None:
        return estimate_pitch_contour(audio, sr, hop=512)

    try:
        pred = crepe.predict(audio.astype(np.float32), sr, viterbi=True, step_size=10, verbose=0)
        if len(pred) == 4:
            times, f0, confidence, _ = pred
        else:
            times, f0, confidence = pred
        f0 = np.where(np.asarray(confidence) > 0.45, np.asarray(f0), np.nan)
        if np.isfinite(f0).any():
            return f0.astype(np.float32), np.asarray(times, dtype=np.float32)
    except Exception as exc:
        log.warning("CREPE pitch tracking unavailable at runtime (%s), using fallback.", exc)

    return estimate_pitch_contour(audio, sr, hop=512)


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


def apply_formant_shift(audio: np.ndarray, sr: int, shift_factor: float) -> np.ndarray:
    if audio.size == 0 or abs(shift_factor - 1.0) < 1e-3:
        return audio
    spec = librosa.stft(audio, n_fft=2048, hop_length=256)
    mag = np.abs(spec)
    phase = np.angle(spec)
    bins = np.arange(mag.shape[0])
    src = np.clip(bins / shift_factor, 0, mag.shape[0] - 1)
    shifted_mag = np.zeros_like(mag)
    for t in range(mag.shape[1]):
        shifted_mag[:, t] = np.interp(bins, src, mag[:, t], left=mag[0, t], right=mag[-1, t])
    rebuilt = shifted_mag * np.exp(1j * phase)
    return librosa.istft(rebuilt, hop_length=256, length=len(audio)).astype(np.float32)


def apply_vibrato(audio: np.ndarray, sr: int, rate_hz: float, depth_cents: float) -> np.ndarray:
    if audio.size == 0:
        return audio
    n = len(audio)
    t = np.arange(n) / sr
    depth_samples = (np.power(2.0, depth_cents / 1200.0) - 1.0) * (sr / (2 * np.pi * max(rate_hz, 0.1)))
    mod = depth_samples * np.sin(2 * np.pi * rate_hz * t)
    idx = np.arange(n) + mod
    idx = np.clip(idx, 0, n - 1)
    return np.interp(np.arange(n), idx, audio).astype(np.float32)


def apply_pitch_drift(audio: np.ndarray, sr: int, depth_cents: float = 8.0, rate_hz: float = 0.2) -> np.ndarray:
    if audio.size == 0:
        return audio
    n = len(audio)
    t = np.arange(n) / sr
    cents = depth_cents * np.sin(2 * np.pi * rate_hz * t)
    ratio = np.power(2.0, cents / 1200.0)
    phase = np.cumsum(ratio)
    phase = (phase - phase[0])
    phase = phase / max(phase[-1], 1.0) * (n - 1)
    return np.interp(np.arange(n), phase, audio).astype(np.float32)


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


def apply_saturation(audio: np.ndarray, drive: float = 1.5) -> np.ndarray:
    sat = np.tanh(audio * drive)
    return (0.7 * audio + 0.3 * sat).astype(np.float32)


def apply_voice_spectral_variation(audio: np.ndarray, sr: int, voice_idx: int) -> np.ndarray:
    if audio.size == 0:
        return audio
    spec = librosa.stft(audio, n_fft=2048, hop_length=512)
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    curve = np.ones_like(freqs, dtype=np.float32)

    if voice_idx == 1:
        band = (freqs >= 2500) & (freqs <= 3500)
        curve[band] *= np.power(10.0, 2.0 / 20.0)
    elif voice_idx == 2:
        band = (freqs >= 4500) & (freqs <= 5500)
        curve[band] *= np.power(10.0, -2.0 / 20.0)
    else:
        band = (freqs >= 7500) & (freqs <= 8500)
        curve[band] *= np.power(10.0, 1.5 / 20.0)

    spec *= curve[:, None]
    return librosa.istft(spec, hop_length=512, length=len(audio)).astype(np.float32)


def spectral_shape_harmony(audio: np.ndarray, sr: int) -> np.ndarray:
    if audio.size == 0:
        return audio
    spec = librosa.stft(audio, n_fft=2048, hop_length=512)
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    mask = np.ones_like(freqs, dtype=np.float32)
    mask[freqs < 150.0] *= np.clip(freqs[freqs < 150.0] / 150.0, 0.0, 1.0)
    mask[freqs > 10000.0] *= np.exp(-(freqs[freqs > 10000.0] - 10000.0) / 3500.0)
    spec *= mask[:, None]
    return librosa.istft(spec, hop_length=512, length=len(audio)).astype(np.float32)


def load_ir(sr: int) -> np.ndarray:
    ir_dir = ENGINE_ROOT / "assets" / "ir"
    candidates = [ir_dir / "studio_room.wav", ir_dir / "plate_reverb.wav", ir_dir / "hall_reverb.wav"]
    existing = [p for p in candidates if p.exists()]

    if existing:
        chosen = random.choice(existing)
        ir, _ = librosa.load(str(chosen), sr=sr, mono=False)
        if ir.ndim == 1:
            ir = np.vstack([ir, ir])
        log.info("Using convolution IR: %s", chosen.name)
        return ir.astype(np.float32)

    ir_len = int(sr * 0.8)
    t = np.linspace(0.0, 1.0, ir_len, endpoint=False)
    decay = np.exp(-5.0 * t)
    left = decay * (0.8 + 0.2 * np.sin(2 * np.pi * 2.0 * t))
    right = decay * (0.8 + 0.2 * np.cos(2 * np.pi * 2.3 * t))
    return np.vstack([left, right]).astype(np.float32)


def convolve_reverb_send(stereo: np.ndarray, sr: int, wet: float = 0.18, pre_delay_ms: float = 25.0) -> np.ndarray:
    wet = max(0.0, min(0.6, wet))
    ir = load_ir(sr)

    predelay = int(sr * pre_delay_ms / 1000.0)
    delayed = np.pad(stereo, ((predelay, 0), (0, 0)))[:len(stereo)] if predelay > 0 else stereo

    # Early reflections
    er_delays = [int(sr * d) for d in (0.012, 0.019, 0.027)]
    er_gains = [0.35, 0.22, 0.14]
    early = np.zeros_like(delayed)
    for d, g in zip(er_delays, er_gains):
        if d <= 0 or d >= len(delayed):
            continue
        early[d:, :] += delayed[:-d, :] * g

    scipy_signal = optional_module("scipy.signal")
    if scipy_signal is not None:
        rev_l = scipy_signal.fftconvolve(delayed[:, 0], ir[0], mode="full")[: len(delayed)]
        rev_r = scipy_signal.fftconvolve(delayed[:, 1], ir[1], mode="full")[: len(delayed)]
    else:
        rev_l = np.convolve(delayed[:, 0], ir[0], mode="full")[: len(delayed)]
        rev_r = np.convolve(delayed[:, 1], ir[1], mode="full")[: len(delayed)]

    tail = np.column_stack([rev_l, rev_r]).astype(np.float32)
    wet_sig = early + tail
    return stereo + wet_sig * wet


def soft_knee_gain_db(level_db: float, threshold_db: float, ratio: float, knee_db: float = 6.0) -> float:
    lower = threshold_db - knee_db / 2.0
    upper = threshold_db + knee_db / 2.0
    if level_db < lower:
        return 0.0
    if level_db > upper:
        compressed_db = threshold_db + (level_db - threshold_db) / ratio
        return compressed_db - level_db
    compressed_db = level_db + (1.0 / ratio - 1.0) * ((level_db - lower) ** 2) / (2.0 * knee_db)
    return compressed_db - level_db


def apply_rms_compressor(stereo: np.ndarray, sr: int, threshold_db: float = -18.0, ratio: float = 2.0,
                         attack_ms: float = 5.0, release_ms: float = 80.0) -> np.ndarray:
    if stereo.size == 0:
        return stereo

    mono = np.mean(stereo, axis=1)
    window = max(1, int(sr * 0.005))
    kernel = np.ones(window, dtype=np.float32) / window
    rms = np.sqrt(np.convolve(np.square(mono), kernel, mode="same") + 1e-10)
    level_db = 20.0 * np.log10(np.maximum(rms, 1e-8))

    target_gain_db = np.array([soft_knee_gain_db(v, threshold_db, ratio, knee_db=6.0) for v in level_db], dtype=np.float32)

    attack = np.exp(-1.0 / max(1.0, sr * attack_ms / 1000.0))
    release = np.exp(-1.0 / max(1.0, sr * release_ms / 1000.0))
    smoothed = np.zeros_like(target_gain_db)
    g = 0.0
    for i, t in enumerate(target_gain_db):
        coeff = attack if t < g else release
        g = coeff * g + (1.0 - coeff) * t
        smoothed[i] = g

    lin = np.power(10.0, smoothed / 20.0)
    return (stereo * lin[:, None]).astype(np.float32)


def apply_deesser(stereo: np.ndarray, sr: int, center_low: float = 5000.0, center_high: float = 8000.0,
                  reduction_db: float = 4.5) -> np.ndarray:
    if stereo.size == 0:
        return stereo

    out = np.copy(stereo)
    for c in range(2):
        x = out[:, c]
        spec = librosa.stft(x, n_fft=2048, hop_length=256)
        mag = np.abs(spec)
        phase = np.angle(spec)
        freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
        band_mask = (freqs >= center_low) & (freqs <= center_high)

        if not np.any(band_mask):
            continue

        band_energy = np.mean(mag[band_mask, :], axis=0)
        threshold = np.percentile(band_energy, 75)
        active = band_energy > threshold
        gain = np.ones_like(band_energy)
        gain[active] = np.power(10.0, -reduction_db / 20.0)

        mag[band_mask, :] *= gain[None, :]
        rebuilt = mag * np.exp(1j * phase)
        out[:, c] = librosa.istft(rebuilt, hop_length=256, length=len(x))

    return out


def apply_basic_eq(stereo: np.ndarray, sr: int) -> np.ndarray:
    if stereo.size == 0:
        return stereo

    out = np.copy(stereo)
    for c in range(2):
        x = out[:, c]
        spec = librosa.stft(x, n_fft=2048, hop_length=512)
        freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
        hp = np.ones_like(freqs)
        hp[freqs < 80] = np.clip(freqs[freqs < 80] / 80.0, 0.0, 1.0)
        presence = np.ones_like(freqs)
        band = (freqs >= 3500) & (freqs <= 5000)
        presence[band] *= np.power(10.0, 2.0 / 20.0)
        spec *= (hp * presence)[:, None]
        out[:, c] = librosa.istft(spec, hop_length=512, length=len(x))
    return out


def apply_limiter(stereo: np.ndarray, sr: int, threshold_db: float = -1.0,
                  attack_ms: float = 1.0, release_ms: float = 50.0) -> np.ndarray:
    threshold = np.power(10.0, threshold_db / 20.0)
    lookahead = max(1, int(sr * 0.001))
    padded = np.pad(stereo, ((lookahead, 0), (0, 0)))
    out = np.copy(stereo)

    attack = np.exp(-1.0 / max(1.0, sr * attack_ms / 1000.0))
    release = np.exp(-1.0 / max(1.0, sr * release_ms / 1000.0))

    gain = 1.0
    for i in range(len(out)):
        future = np.max(np.abs(padded[i:i + lookahead]))
        desired = min(1.0, threshold / max(future, 1e-9))
        coeff = attack if desired < gain else release
        gain = coeff * gain + (1.0 - coeff) * desired
        out[i] *= gain
    return out


def stereo_widen(stereo: np.ndarray, width_gain: float = 1.12) -> np.ndarray:
    m = (stereo[:, 0] + stereo[:, 1]) * 0.5
    s = (stereo[:, 0] - stereo[:, 1]) * 0.5 * width_gain
    l = m + s
    r = m - s
    return np.column_stack([l, r]).astype(np.float32)


def normalize_lufs_approx(stereo: np.ndarray, target_lufs: float = -14.0) -> np.ndarray:
    if stereo.size == 0:
        return stereo
    mono = np.mean(stereo, axis=1)
    rms = float(np.sqrt(np.mean(np.square(mono)) + 1e-12))
    current_db = 20.0 * np.log10(max(rms, 1e-9))
    gain_db = target_lufs - current_db
    gain = 10.0 ** (gain_db / 20.0)
    return stereo * gain


def apply_bus_saturation(stereo: np.ndarray, drive: float = 1.15) -> np.ndarray:
    return np.tanh(stereo * drive).astype(np.float32)


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

    f0, f0_times = estimate_pitch_contour_with_crepe(y, sr)

    detected_ctx = detect_music_context(y, sr)
    ctx = MusicContext(key=detected_ctx.key, scale=detected_ctx.scale)
    config["detected_key"] = ctx.key
    config["detected_scale"] = ctx.scale
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    log.info("Detected musical context from audio: key=%s scale=%s", ctx.key, ctx.scale)

    try:
        user_mix = float(config.get("mix", 1.0))
    except Exception:
        user_mix = 1.0

    user_mix = float(np.clip(user_mix, 0.0, 1.0))

    try:
        reverb_intensity = float(config.get("reverb_intensity", 0.35))
    except Exception:
        reverb_intensity = 0.35
    reverb_intensity = float(np.clip(reverb_intensity, 0.0, 1.0))

    voices = max(1, min(4, int(float(config.get("voices", 4)))))
    scale_pcs = scale_pitch_classes(ctx)
    log.info("Render parameters: voices=%d mix=%.2f reverb_intensity=%.2f", voices, user_mix, reverb_intensity)

    lead_gain = 0.60
    harmony_bus_gain = 0.40 * user_mix

    out_l = np.zeros_like(y, dtype=np.float32)
    out_r = np.zeros_like(y, dtype=np.float32)

    dry_l, dry_r = constant_power_pan(y.astype(np.float32), 0.0)
    out_l += dry_l * lead_gain
    out_r += dry_r * lead_gain

    shift_cache: dict[tuple[int, int, float], np.ndarray] = {}
    harmony_segments = 0
    harmony_voices_written = 0

    formant_factors = {1: 1.02, 2: 0.97, 3: 1.05}

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
            melody_midi = fallback_melody_midi(y[s0:s1], sr)
        else:
            melody_midi = float(np.median([hz_to_midi(v) for v in seg_f0]))
        tuned_midi = nearest_scale_midi(melody_midi, scale_pcs)
        tune_shift = tuned_midi - melody_midi

        seg_audio_raw = y[s0:s1].astype(np.float32)
        if abs(tune_shift) >= 0.1:
            tuned_seg = pitch_shift_natural(seg_audio_raw, sr, tune_shift, use_formant=True)
            seg_audio = (0.2 * seg_audio_raw + 0.8 * tuned_seg).astype(np.float32)
        else:
            seg_audio = seg_audio_raw

        seg_env = build_segment_envelope(len(seg_audio), sr, crossfade_ms=30.0)
        seg_audio *= seg_env

        chord_pcs = chord_pitch_classes(ctx, degree)
        voice_targets = make_voice_targets(tuned_midi, chord_pcs, voices=voices)
        harmony_count = max(1, len(voice_targets) - 1)
        harmony_segments += 1

        for idx, target in enumerate(voice_targets):
            if idx == 0:
                continue

            rng = random.Random((seg_idx + 1) * 1000 + idx)
            detune = rng.uniform(-0.08, 0.08)
            delay_samples = int(sr * rng.uniform(0.005, 0.035))

            steps = (target - tuned_midi) + detune
            if abs(steps) < 0.1:
                continue

            cache_key = (sr, len(seg_audio), round(float(steps), 3))
            shifted = shift_cache.get(cache_key)
            if shifted is None:
                shifted = pitch_shift_natural(seg_audio, sr, steps, use_formant=True)
                shift_cache[cache_key] = shifted

            shifted = apply_formant_shift(shifted, sr, formant_factors.get(idx, 1.0))
            shifted = apply_vibrato(shifted, sr, rate_hz=rng.uniform(4.5, 6.5), depth_cents=rng.uniform(14.0, 20.0))
            shifted = apply_pitch_drift(shifted, sr, depth_cents=8.0, rate_hz=0.2)
            shifted = spectral_shape_harmony(shifted, sr)
            shifted = apply_voice_spectral_variation(shifted, sr, idx)
            shifted = apply_chorus(shifted, sr, rate_hz=0.2, depth_ms=5.0, base_delay_ms=20.0)
            shifted = apply_saturation(shifted, drive=rng.uniform(1.3, 1.8))

            if delay_samples > 0:
                shifted = np.pad(shifted, (delay_samples, 0))[: len(seg_audio)]

            if idx == 1:
                pan = -0.35
            elif idx == 2:
                pan = 0.35
            else:
                pan = -0.65 if (seg_idx % 2 == 0) else 0.65

            v_l, v_r = constant_power_pan(shifted.astype(np.float32), pan)
            stereo_offset = int(sr * rng.uniform(0.001, 0.004))
            if stereo_offset > 0:
                if pan < 0:
                    v_r = np.pad(v_r, (stereo_offset, 0))[: len(v_r)]
                else:
                    v_l = np.pad(v_l, (stereo_offset, 0))[: len(v_l)]

            seg_len = s1 - s0
            mix_len = min(seg_len, len(v_l), len(v_r))
            if mix_len <= 0:
                continue

            per_voice_gain = harmony_bus_gain / harmony_count
            out_l[s0:s0 + mix_len] += v_l[:mix_len] * per_voice_gain
            out_r[s0:s0 + mix_len] += v_r[:mix_len] * per_voice_gain
            harmony_voices_written += 1

    if harmony_voices_written == 0:
        log.warning("No harmony voices were rendered from timeline segments; applying global fallback harmonies.")
        fallback_steps = [4.0, 7.0]
        for idx, st in enumerate(fallback_steps):
            shifted = pitch_shift_natural(y.astype(np.float32), sr, st, use_formant=True)
            shifted = apply_formant_shift(shifted, sr, 1.02 if idx == 0 else 0.97)
            shifted = apply_saturation(shifted, drive=1.5)
            pan = -0.35 if idx == 0 else 0.35
            v_l, v_r = constant_power_pan(shifted, pan)
            per_voice_gain = harmony_bus_gain / len(fallback_steps)
            out_l[:len(v_l)] += v_l * per_voice_gain
            out_r[:len(v_r)] += v_r * per_voice_gain
        harmony_voices_written = len(fallback_steps)

    log.info("Harmony render summary: segments=%d voices_written=%d", harmony_segments, harmony_voices_written)

    vocal_bus = np.column_stack([out_l, out_r]).astype(np.float32)
    vocal_bus = apply_basic_eq(vocal_bus, sr)
    vocal_bus = apply_deesser(vocal_bus, sr, reduction_db=4.5)
    vocal_bus = apply_rms_compressor(vocal_bus, sr, threshold_db=-18.0, ratio=2.0, attack_ms=5.0, release_ms=80.0)

    wet_amount = 0.10 + (0.35 * reverb_intensity)
    enhanced = convolve_reverb_send(vocal_bus, sr, wet=wet_amount, pre_delay_ms=25.0)
    enhanced = stereo_widen(enhanced, width_gain=1.15)
    enhanced = apply_limiter(enhanced, sr, threshold_db=-1.0, attack_ms=1.0, release_ms=50.0)
    enhanced = apply_bus_saturation(enhanced, drive=1.15)
    enhanced = normalize_lufs_approx(enhanced, target_lufs=-14.0)
    enhanced = safe_normalize(enhanced, target_peak=np.power(10.0, -1.0 / 20.0))
    sf.write(str(out_path), enhanced, sr)

    mastered = normalize_lufs_approx(enhanced, target_lufs=-14.0)
    mastered = apply_limiter(mastered, sr, threshold_db=-1.0, attack_ms=1.0, release_ms=50.0)
    mastered = apply_bus_saturation(mastered, drive=1.15)
    mastered = safe_normalize(mastered, target_peak=np.power(10.0, -1.0 / 20.0))
    sf.write(str(mastered_out_path), mastered, sr)

    log.info("Harmonized audio exported: %s", out_path)
    log.info("Mastered harmonized audio exported: %s", mastered_out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
