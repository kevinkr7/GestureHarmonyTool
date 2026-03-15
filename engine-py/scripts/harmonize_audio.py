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


def midi_to_hz(midi: float) -> float:
    return float(440.0 * np.power(2.0, (midi - 69.0) / 12.0))


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
    base_oct = int(melody_midi // 12) * 12
    root = chord_pcs[0]
    third = chord_pcs[1 % len(chord_pcs)]
    fifth = chord_pcs[2 % len(chord_pcs)]
    raw = [base_oct + root, base_oct + third, base_oct + fifth, melody_midi + 12]
    out = []
    for i, v in enumerate(raw[: max(1, min(voices, 4))]):
        if i > 0 and out and v <= out[-1] + 2.5:
            v += 12
        out.append(v)
    return out




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


def apply_saturation(audio: np.ndarray, drive: float = 1.5) -> np.ndarray:
    sat = np.tanh(audio * drive)
    return (0.7 * audio + 0.3 * sat).astype(np.float32)


def synth_oscillator_voice(freq: float, length: int, sr: int, seed: int) -> np.ndarray:
    if length <= 0:
        return np.array([], dtype=np.float32)
    rng = random.Random(seed)
    t = np.arange(length) / sr

    vibr_rate = rng.uniform(4.5, 6.5)
    vibr_depth_cents = rng.uniform(8.0, 18.0)
    drift_rate = 0.2
    drift_depth_cents = rng.uniform(3.0, 8.0)

    cents = vibr_depth_cents * np.sin(2 * np.pi * vibr_rate * t)
    cents += drift_depth_cents * np.sin(2 * np.pi * drift_rate * t + rng.uniform(0, 2 * np.pi))
    ratio = np.power(2.0, cents / 1200.0)

    phase = 2 * np.pi * np.cumsum((freq * ratio) / sr)
    sig = np.zeros(length, dtype=np.float32)
    for h in range(1, 11):
        amp = 1.0 / h
        rand_phase = rng.uniform(0, 2 * np.pi)
        sig += amp * np.sin(h * phase + rand_phase).astype(np.float32)

    peak = np.max(np.abs(sig))
    if peak > 1e-8:
        sig = sig / peak

    atk = max(1, int(sr * 0.02))
    rel = max(1, int(sr * 0.04))
    env = np.ones(length, dtype=np.float32)
    env[:atk] = np.linspace(0, 1, atk)
    env[-rel:] = np.linspace(1, 0, rel)
    return (sig * env).astype(np.float32)


def detune_freq(freq: float, cents: float) -> float:
    return float(freq * np.power(2.0, cents / 1200.0))


def apply_sample_delay(audio: np.ndarray, samples: int) -> np.ndarray:
    if samples <= 0:
        return audio
    return np.pad(audio, (samples, 0))[:len(audio)]


def build_choir_layer(freq: float, length: int, sr: int, seed: int, detune_cents: float, delay_ms: float) -> np.ndarray:
    layer = synth_oscillator_voice(detune_freq(freq, detune_cents), length, sr, seed)
    delay_samples = int(sr * max(0.0, delay_ms) / 1000.0)
    return apply_sample_delay(layer, delay_samples)


def transfer_spectral_envelope(vocal_seg: np.ndarray, synth_seg: np.ndarray, sr: int) -> np.ndarray:
    if vocal_seg.size == 0 or synth_seg.size == 0:
        return synth_seg.astype(np.float32)

    n_fft = 2048
    hop = 256
    v_stft = librosa.stft(vocal_seg, n_fft=n_fft, hop_length=hop)
    s_stft = librosa.stft(synth_seg, n_fft=n_fft, hop_length=hop)

    v_mag = np.abs(v_stft)
    s_mag = np.abs(s_stft)
    s_phase = np.angle(s_stft)

    frames = min(v_mag.shape[1], s_mag.shape[1])
    out_mag = np.copy(s_mag)
    for t in range(frames):
        env = v_mag[:, t:t + 1]
        s_frame = s_mag[:, t:t + 1]
        s_norm = s_frame / (np.mean(s_frame) + 1e-8)
        out_mag[:, t:t + 1] = s_norm * env

    if s_mag.shape[1] > frames and frames > 0:
        out_mag[:, frames:] = out_mag[:, frames - 1:frames]

    out_stft = out_mag * np.exp(1j * s_phase)
    return librosa.istft(out_stft, hop_length=hop, length=len(synth_seg)).astype(np.float32)


def apply_chorus(audio: np.ndarray, sr: int, rate_hz: float = 0.22, depth_ms: float = 4.5, base_delay_ms: float = 18.0) -> np.ndarray:
    if audio.size == 0:
        return audio
    depth = int(sr * depth_ms / 1000.0)
    base = int(sr * base_delay_ms / 1000.0)
    out = np.copy(audio)
    if base <= 0:
        return out

    n = np.arange(len(audio))
    lfo = (np.sin(2 * np.pi * rate_hz * (n / sr)) + 1.0) * 0.5
    delays = base + (lfo * depth).astype(int)
    for i in range(base + depth, len(audio)):
        out[i] += 0.28 * audio[i - delays[i]]
    return out


def load_ir(sr: int) -> np.ndarray:
    ir_dir = ENGINE_ROOT / "assets" / "ir"
    candidates = [ir_dir / "studio_room.wav", ir_dir / "plate_reverb.wav", ir_dir / "hall_reverb.wav"]
    existing = [p for p in candidates if p.exists()]
    if existing:
        plate = ir_dir / "plate_reverb.wav"
        chosen = plate if plate.exists() else random.choice(existing)
        ir, _ = librosa.load(str(chosen), sr=sr, mono=False)
        if ir.ndim == 1:
            ir = np.vstack([ir, ir])
        log.info("Using convolution IR: %s", chosen.name)
        return ir.astype(np.float32)

    t = np.linspace(0.0, 1.0, int(sr * 0.8), endpoint=False)
    decay = np.exp(-5.0 * t)
    return np.vstack([
        decay * (0.8 + 0.2 * np.sin(2 * np.pi * 2.0 * t)),
        decay * (0.8 + 0.2 * np.cos(2 * np.pi * 2.2 * t)),
    ]).astype(np.float32)


def convolve_reverb_send(stereo: np.ndarray, sr: int, wet: float, pre_delay_ms: float = 25.0) -> np.ndarray:
    wet = float(np.clip(wet, 0.0, 0.6))
    ir = load_ir(sr)

    predelay = int(sr * pre_delay_ms / 1000.0)
    dry_delayed = np.pad(stereo, ((predelay, 0), (0, 0)))[: len(stereo)] if predelay > 0 else stereo

    early = np.zeros_like(dry_delayed)
    for d, g in [(0.012, 0.30), (0.019, 0.22), (0.028, 0.15)]:
        ds = int(sr * d)
        if 0 < ds < len(dry_delayed):
            early[ds:, :] += dry_delayed[:-ds, :] * g

    scipy_signal = optional_module("scipy.signal")
    if scipy_signal is not None:
        rev_l = scipy_signal.fftconvolve(dry_delayed[:, 0], ir[0], mode="full")[: len(dry_delayed)]
        rev_r = scipy_signal.fftconvolve(dry_delayed[:, 1], ir[1], mode="full")[: len(dry_delayed)]
    else:
        rev_l = np.convolve(dry_delayed[:, 0], ir[0], mode="full")[: len(dry_delayed)]
        rev_r = np.convolve(dry_delayed[:, 1], ir[1], mode="full")[: len(dry_delayed)]

    tail = np.column_stack([rev_l, rev_r]).astype(np.float32)
    return stereo + (early + tail) * wet


def apply_limiter(stereo: np.ndarray, sr: int, threshold_db: float = -1.0) -> np.ndarray:
    threshold = np.power(10.0, threshold_db / 20.0)
    lookahead = max(1, int(sr * 0.001))
    padded = np.pad(stereo, ((lookahead, 0), (0, 0)))
    out = np.copy(stereo)

    attack = np.exp(-1.0 / (sr * 0.001))
    release = np.exp(-1.0 / (sr * 0.05))

    gain = 1.0
    for i in range(len(out)):
        future = np.max(np.abs(padded[i:i + lookahead]))
        desired = min(1.0, threshold / max(future, 1e-9))
        coeff = attack if desired < gain else release
        gain = coeff * gain + (1.0 - coeff) * desired
        out[i] *= gain
    return out


def normalize_lufs_approx(stereo: np.ndarray, target_lufs: float = -14.0) -> np.ndarray:
    mono = np.mean(stereo, axis=1)
    rms = float(np.sqrt(np.mean(np.square(mono)) + 1e-12))
    current_db = 20.0 * np.log10(max(rms, 1e-9))
    gain = np.power(10.0, (target_lufs - current_db) / 20.0)
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

    y, sr = librosa.load(str(input_wav), sr=None, mono=True)
    if y.ndim != 1:
        y = librosa.to_mono(y)

    f0, f0_times = estimate_pitch_contour_with_crepe(y, sr)

    detected_ctx = detect_music_context(y, sr)
    ctx = MusicContext(key=detected_ctx.key, scale=detected_ctx.scale)
    config["detected_key"] = ctx.key
    config["detected_scale"] = ctx.scale
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

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

    lead_gain = 0.60
    harmony_bus_gain = 0.40 * user_mix

    out_l = np.zeros_like(y, dtype=np.float32)
    out_r = np.zeros_like(y, dtype=np.float32)

    dry_l, dry_r = constant_power_pan(y.astype(np.float32), 0.0)
    out_l += dry_l * lead_gain
    out_r += dry_r * lead_gain

    rendered_voices = 0

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

        vocal_seg = y[s0:s1].astype(np.float32)
        if vocal_seg.size < 512:
            continue

        mask = (f0_times >= start) & (f0_times < end)
        seg_f0 = f0[mask]
        seg_f0 = seg_f0[np.isfinite(seg_f0)]

        if seg_f0.size == 0:
            melody_midi = fallback_melody_midi(vocal_seg, sr)
        else:
            melody_midi = float(np.median([hz_to_midi(v) for v in seg_f0]))

        tuned_midi = nearest_scale_midi(melody_midi, scale_pcs)
        chord_pcs = chord_pitch_classes(ctx, degree)
        voice_targets = make_voice_targets(tuned_midi, chord_pcs, voices=voices)
        harmony_count = max(1, len(voice_targets) - 1)

        seg_env = build_segment_envelope(len(vocal_seg), sr, crossfade_ms=30.0)

        for idx, target in enumerate(voice_targets):
            if idx == 0:
                continue

            seed = (seg_idx + 1) * 1000 + idx
            base_freq = midi_to_hz(target)
            rng = random.Random(seed)

            layer_a = build_choir_layer(base_freq, len(vocal_seg), sr, seed + 1, 0.0, 0.0)
            layer_b = build_choir_layer(base_freq, len(vocal_seg), sr, seed + 2, 6.0, rng.uniform(8.0, 25.0))
            layer_c = build_choir_layer(base_freq, len(vocal_seg), sr, seed + 3, -6.0, rng.uniform(8.0, 25.0))
            synth = (layer_a + 0.85 * layer_b + 0.85 * layer_c).astype(np.float32)

            synth = transfer_spectral_envelope(vocal_seg, synth, sr)
            synth = apply_formant_shift(synth, sr, {1: 1.02, 2: 0.97, 3: 1.05}.get(idx, 1.0))
            synth = apply_voice_spectral_variation(synth, sr, idx)
            synth = apply_chorus(synth, sr)
            synth = apply_saturation(synth, drive=rng.uniform(1.3, 1.8))
            synth *= seg_env

            pan_positions = [-0.6, -0.3, 0.3, 0.6]
            pan = pan_positions[(idx - 1) % len(pan_positions)]

            v_l, v_r = constant_power_pan(synth.astype(np.float32), pan)
            stereo_offset = int(sr * rng.uniform(0.001, 0.004))
            if stereo_offset > 0:
                if pan < 0:
                    v_r = np.pad(v_r, (stereo_offset, 0))[: len(v_r)]
                else:
                    v_l = np.pad(v_l, (stereo_offset, 0))[: len(v_l)]

            mix_len = min(s1 - s0, len(v_l), len(v_r))
            if mix_len <= 0:
                continue

            gain = harmony_bus_gain / harmony_count
            out_l[s0:s0 + mix_len] += v_l[:mix_len] * gain
            out_r[s0:s0 + mix_len] += v_r[:mix_len] * gain
            rendered_voices += 1

    if rendered_voices == 0:
        log.warning("No choir voices rendered from timeline; using fallback sustained chord layer.")
        for i, st in enumerate([4.0, 7.0]):
            freq = midi_to_hz(nearest_scale_midi(hz_to_midi(220.0) + st, scale_pcs))
            synth = synth_oscillator_voice(freq, len(y), sr, 7000 + i)
            synth = transfer_spectral_envelope(y.astype(np.float32), synth, sr)
            pan = -0.35 if i == 0 else 0.35
            v_l, v_r = constant_power_pan(synth, pan)
            gain = harmony_bus_gain / 2.0
            out_l[:len(v_l)] += v_l * gain
            out_r[:len(v_r)] += v_r * gain

    vocal_bus = np.column_stack([out_l, out_r]).astype(np.float32)
    vocal_bus[:, 0] = apply_chorus(vocal_bus[:, 0], sr, rate_hz=0.18, depth_ms=4.0, base_delay_ms=16.0)
    vocal_bus[:, 1] = apply_chorus(vocal_bus[:, 1], sr, rate_hz=0.21, depth_ms=4.5, base_delay_ms=18.0)
    vocal_bus = apply_saturation(vocal_bus, drive=1.18)

    wet_amount = 0.10 + (0.35 * reverb_intensity)
    enhanced = convolve_reverb_send(vocal_bus, sr, wet=wet_amount, pre_delay_ms=25.0)
    enhanced = apply_limiter(enhanced, sr, threshold_db=-1.0)
    enhanced = apply_bus_saturation(enhanced, drive=1.15)
    enhanced = normalize_lufs_approx(enhanced, target_lufs=-14.0)
    enhanced = safe_normalize(enhanced, target_peak=np.power(10.0, -1.0 / 20.0))
    sf.write(str(out_path), enhanced, sr)

    mastered = normalize_lufs_approx(enhanced, target_lufs=-14.0)
    mastered = apply_limiter(mastered, sr, threshold_db=-1.0)
    mastered = apply_bus_saturation(mastered, drive=1.15)
    mastered = safe_normalize(mastered, target_peak=np.power(10.0, -1.0 / 20.0))
    sf.write(str(mastered_out_path), mastered, sr)

    log.info("Harmonized choir audio exported: %s", out_path)
    log.info("Mastered choir audio exported: %s", mastered_out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
