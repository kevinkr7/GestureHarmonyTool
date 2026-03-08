from __future__ import annotations

import json
import math
import os
import sys
from typing import List, Optional, Tuple

import numpy as np
import librosa
import soundfile as sf

# ----------------------------
# Enhanced Music Theory & Configuration
# ----------------------------

# Configuration for the "Lush" sound
STEREO_WIDTH = 0.85  # 0.0 (Mono) to 1.0 (Super Wide)
MIX_WET = 0.70       # Harmony volume relative to original
MIX_DRY = 0.80       # Original vocal volume

KEY_TO_SEMITONE = {
    "C": 0,  "B#": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
    "E": 4,  "Fb": 4, "F": 5,  "E#": 5, "F#": 6, "Gb": 6, "G": 7,
    "G#": 8, "Ab": 8, "A": 9,  "A#": 10, "Bb": 10, "B": 11, "Cb": 11
}

# Extended Chord Voicings (Relative to Root)
# Adding 7ths and 9ths creates that modern, suspended Imogen Heap vocal pad sound.
DEGREE_TO_INTERVALS = {
    "I":   [0, 4, 7, 11, 14],  # Major 7/9
    "II":  [0, 3, 7, 10, 14],  # Minor 7/9
    "III": [0, 3, 7, 10],      # Minor 7
    "IV":  [0, 4, 7, 11, 14],  # Major 7/9
    "V":   [0, 4, 7, 10, 14],  # Dominant 7/9
    "VI":  [0, 3, 7, 10, 14],  # Minor 7/9
    "VII": [0, 3, 6, 10],      # Half-diminished 7
}

# Diatonic root offsets for Major Scale (I=0, ii=2, iii=4, IV=5, V=7, vi=9, vii=11)
DEGREE_TO_ROOT_OFFSET = {
    "I": 0, "II": 2, "III": 4, "IV": 5, "V": 7, "VI": 9, "VII": 11
}

# ----------------------------
# Audio & Math Helpers
# ----------------------------

def hz_to_midi(h: float) -> float:
    if h <= 0: return 0.0
    return 69.0 + 12.0 * math.log2(h / 440.0)

def normalize_key_name(k: str) -> str:
    return k.strip().replace("♯", "#").replace("♭", "b")

def get_chord_pitch_classes(key_semitone: int, degree: str) -> List[int]:
    """Generates the absolute pitch classes for a given scale degree."""
    degree_upper = degree.strip().upper()
    
    # Extract base Roman numeral (ignoring min/maj suffixes for this mapping)
    base_num = ''.join(c for c in degree_upper if c in 'IV')
    if base_num not in DEGREE_TO_ROOT_OFFSET:
        return [(key_semitone + 0) % 12, (key_semitone + 4) % 12, (key_semitone + 7) % 12] # Fallback to Tonic Maj
        
    root_offset = DEGREE_TO_ROOT_OFFSET[base_num]
    abs_root = (key_semitone + root_offset) % 12
    intervals = DEGREE_TO_INTERVALS.get(base_num, [0, 4, 7])
    
    return [(abs_root + i) % 12 for i in intervals]

def build_vocoder_voicing(median_midi: float, chord_pcs: List[int]) -> List[float]:
    """
    Intelligently builds a spread voicing around the detected melody note.
    Instead of just matching the closest notes, it creates a wide chord stack:
    - Bass note (Root, 1-2 octaves down)
    - Mid notes (3rd/5th/7th below or around melody)
    - High notes (above melody)
    """
    if not chord_pcs or not np.isfinite(median_midi):
        return []

    root_pc = chord_pcs[0]
    voicing = []
    base_octave_c = int((median_midi // 12) * 12)
    
    # 1. Add deep bass root (1 octave below current octave)
    bass_note = root_pc + (base_octave_c - 12)
    # Prevent bass from being too sub-sonic
    if bass_note < 36: bass_note += 12 
    voicing.append(bass_note)
    
    # 2. Build middle/high harmony stack
    for pc in chord_pcs[1:]:
        # Find closest instance of this pitch class to the melody
        cand1 = pc + base_octave_c
        cand2 = pc + base_octave_c - 12
        cand3 = pc + base_octave_c + 12
        
        # Pick the one closest to the melody to keep the chord tight
        best_cand = min([cand1, cand2, cand3], key=lambda x: abs(x - median_midi))
        
        # Avoid duplicating the exact melody note in the harmony stack
        if abs(best_cand - median_midi) > 0.5:
            voicing.append(best_cand)

    # 3. Add a high root or 5th for "air" (1 octave up)
    voicing.append(chord_pcs[2 % len(chord_pcs)] + base_octave_c + 12)
    
    # Remove duplicates and sort
    return sorted(list(set(voicing)))

def stereo_pan(audio_mono: np.ndarray, pan: float) -> Tuple[np.ndarray, np.ndarray]:
    """
    Constant-power stereo panning.
    pan: -1.0 (100% Left) to 1.0 (100% Right)
    """
    pan = max(-1.0, min(1.0, pan))
    angle = (pan + 1.0) * (np.pi / 4.0)
    left = audio_mono * math.cos(angle)
    right = audio_mono * math.sin(angle)
    return left, right

# ----------------------------
# Main Processing Pipeline
# ----------------------------

def main():
    if len(sys.argv) < 2:
        print("Usage: python harmonize_enhanced.py <session_path>")
        sys.exit(2)

    session = sys.argv[1]
    audio_path = os.path.join(session, "output.wav")
    timeline_path = os.path.join(session, "timeline.json")
    config_path = os.path.join(session, "config.json")
    out_path = os.path.join(session, "harmonized_enhanced.wav")

    # Error handling for missing files
    for path, name in [(audio_path, "output.wav"), (timeline_path, "timeline.json"), (config_path, "config.json")]:
        if not os.path.exists(path):
            print(f"Missing {name}: {path}")
            sys.exit(1)

    # Load Config
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
        
    key_name = normalize_key_name(str(config.get("key", "C")))
    key_semitone = KEY_TO_SEMITONE.get(key_name, 0)
    user_mix = float(config.get("mix", MIX_WET))

    # Load Timeline
    with open(timeline_path, "r", encoding="utf-8") as f:
        timeline = json.load(f)

    # Load Audio
    print(f"Loading {audio_path}...")
    y_dry, sr = librosa.load(audio_path, sr=None, mono=True)
    if y_dry.ndim != 1:
        y_dry = librosa.to_mono(y_dry)

    # Pitch Tracking (hop_length 512 for good time resolution)
    print("Analyzing pitch contour (pyin)...")
    hop = 512
    f0_hz, _, _ = librosa.pyin(y_dry, fmin=65, fmax=1046, sr=sr, hop_length=hop)
    f0_times = librosa.frames_to_time(np.arange(len(f0_hz)), sr=sr, hop_length=hop)

    # Stereo Output Buffers
    out_L = np.zeros_like(y_dry)
    out_R = np.zeros_like(y_dry)

    # Add Dry Signal (Center Panned)
    dry_L, dry_R = stereo_pan(y_dry, 0.0)
    out_L += dry_L * MIX_DRY
    out_R += dry_R * MIX_DRY

    print(f"Generating Imogen Heap Style Harmony (Key: {key_name})...")

    # Process each timeline segment
    for seg in timeline:
        try:
            start, end = float(seg["start"]), float(seg["end"])
            degree = str(seg["degree"]).strip()
        except KeyError:
            continue

        if end <= start: continue

        # 1. Get pitch classes for this chord
        chord_pcs = get_chord_pitch_classes(key_semitone, degree)
        
        # 2. Find median pitch of the original audio in this segment
        mask = (f0_times >= start) & (f0_times < end)
        seg_f0 = f0_hz[mask]
        seg_f0 = seg_f0[np.isfinite(seg_f0)]
        
        if seg_f0.size == 0:
            continue # Unvoiced/Silence

        median_midi = float(np.median([hz_to_midi(h) for h in seg_f0]))

        # 3. Build the Voicing Stack
        voicing_midis = build_vocoder_voicing(median_midi, chord_pcs)
        
        s0 = max(0, int(round(start * sr)))
        s1 = min(len(y_dry), int(round(end * sr)))
        if s1 <= s0: continue

        seg_audio = y_dry[s0:s1]
        
        print(f"[{start:.2f}s - {end:.2f}s] {degree} Chord. Melody: {median_midi:.1f}. Generating {len(voicing_midis)} voices...")

        # 4. Generate each voice and pan it
        for i, target_midi in enumerate(voicing_midis):
            steps = target_midi - median_midi
            
            # Skip shifting if it's identical to melody (avoids phasing)
            if abs(steps) < 0.2:
                continue

            # High-quality pitch shift (24 bins per octave reduces artifacts)
            shifted = librosa.effects.pitch_shift(seg_audio, sr=sr, n_steps=steps, bins_per_octave=24)
            
            # Panning Logic:
            # Bass is center (0.0). Other voices alternate Left/Right, wider as they get higher.
            if i == 0: 
                pan_val = 0.0 
            else:
                side = -1.0 if i % 2 != 0 else 1.0
                spread = (i / len(voicing_midis)) * STEREO_WIDTH
                pan_val = side * spread
            
            # Pan and mix
            voice_L, voice_R = stereo_pan(shifted, pan_val)
            
            # Lower the volume of extreme high/low extensions slightly
            voice_gain = user_mix * (0.8 if abs(steps) > 12 else 1.0)
            
            out_L[s0:s1] += voice_L * voice_gain
            out_R[s0:s1] += voice_R * voice_gain

    # 5. Master Bus Processing (Normalization & Limiting)
    print("Finalizing mixdown...")
    
    # Interleave L and R channels
    stereo_out = np.vstack((out_L, out_R)).T
    
    # Soft Clipping / Peak Normalization
    peak = np.max(np.abs(stereo_out))
    if peak > 0.95:
        # Normalize to -0.5 dB to prevent digital clipping
        stereo_out = (stereo_out / peak) * 0.944  

    # 6. Export
    sf.write(out_path, stereo_out, sr)
    print(f"✨ LUSH HARMONY EXPORTED TO: {out_path} ✨")

if __name__ == "__main__":
    main()