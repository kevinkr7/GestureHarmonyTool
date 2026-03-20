from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
import re

# New imports for key detection
import librosa
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
ENGINE_ROOT = SCRIPT_DIR.parent

PLUGIN_CONFIG_PATH = ENGINE_ROOT / "config" / "plugin_config.json"
TEMPLATE_PATH = ENGINE_ROOT / "templates" / "harmony_template.rpp"
TEMPLATE_VOCAL = ENGINE_ROOT / "templates" / "Media" / "input_vocal-imported.wav"
TEMPLATE_MIDI = ENGINE_ROOT / "templates" / "Media" / "chords-imported.mid"
TEMPLATE_RENDERED = ENGINE_ROOT / "templates" / "harmonized.wav"


try:
    import pretty_midi
except ImportError:  # pragma: no cover
    pretty_midi = None

VALID_DEGREES = {"ONE", "TWO_MINOR", "THREE_MINOR", "FOUR"}

def detect_song_key(audio_path: Path) -> tuple[int, str]:
    """Analyzes audio to detect the root MIDI note and scale type (major/minor)."""
    print(f"Analyzing vocal track to detect key: {audio_path.name}...")
    try:
        y, sr = librosa.load(str(audio_path), sr=None, mono=True)
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
        chroma_sum = np.sum(chroma, axis=1)

        # Krumhansl-Schmuckler key profiles
        maj_profile = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
        min_profile = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]

        # Correlate the audio's pitch heatmap against the 12 possible major/minor keys
        maj_corrs = [np.corrcoef(chroma_sum, np.roll(maj_profile, i))[0, 1] for i in range(12)]
        min_corrs = [np.corrcoef(chroma_sum, np.roll(min_profile, i))[0, 1] for i in range(12)]

        best_maj = int(np.argmax(maj_corrs))
        best_min = int(np.argmax(min_corrs))

        note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

        if maj_corrs[best_maj] > min_corrs[best_min]:
            print(f"--> Auto-Detected Key: {note_names[best_maj]} Major")
            return 48 + best_maj, "major"  # 48 is C3
        else:
            print(f"--> Auto-Detected Key: {note_names[best_min]} Minor")
            return 48 + best_min, "minor"
            
    except Exception as e:
        print(f"Key detection failed: {e}. Defaulting to C Major.")
        return 48, "major"


def normalize_timeline_segments(raw_timeline, min_duration: float = 0.05) -> list[dict]:
    cleaned = []
    for seg in raw_timeline:
        start = float(seg.get("start", 0.0))
        end = float(seg.get("end", start))
        degree = str(seg.get("degree", "ONE")).upper()

        if degree not in VALID_DEGREES and degree != "MUTE":
            degree = "MUTE"
        if end <= start:
            continue

        cleaned.append({"start": start, "end": end, "degree": degree})

    cleaned.sort(key=lambda seg: (seg["start"], seg["end"], seg["degree"]))

    normalized = []
    for seg in cleaned:
        start = seg["start"]
        end = seg["end"]

        if normalized:
            previous = normalized[-1]
            if start < previous["end"]:
                start = previous["end"]
            if seg["degree"] == previous["degree"] and start <= previous["end"] + 1e-6:
                previous["end"] = max(previous["end"], end)
                continue

        if end - start < min_duration:
            continue

        normalized.append({"start": start, "end": end, "degree": seg["degree"]})

    return normalized


def _load_plugin_config() -> dict:
    if not PLUGIN_CONFIG_PATH.exists():
        return {"vst_name": "Harmony Engine", "reaper_path": "reaper"}
    with PLUGIN_CONFIG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def detect_vst_plugin(vst_name: str | None = None) -> bool:
    config = _load_plugin_config()
    target = (vst_name or config.get("vst_name") or "Harmony Engine").lower()

    search_roots = [
        Path("C:/Program Files/Common Files/VST3"),
        Path("C:/Program Files/VSTPlugins"),
        Path("C:/Program Files/Steinberg/VstPlugins"),
    ]

    for root in search_roots:
        if not root.exists():
            continue
        for candidate in root.rglob("*.vst3"):
            if target in candidate.stem.lower():
                print(f"Detected VST plugin: {candidate}")
                return True

    print("Harmony Engine VST not found. Please install the plugin.")
    return False


def generate_chord_midi(timeline_path: Path | str, output_midi: Path | str, root_note: int, scale_type: str) -> Path:
    if pretty_midi is None:
        raise RuntimeError("pretty_midi is required to generate MIDI chords")

    with Path(timeline_path).open("r", encoding="utf-8") as f:
        raw_timeline = json.load(f)

    blocks = normalize_timeline_segments(raw_timeline)
    sounding_blocks = [block for block in blocks if block["degree"] != "MUTE"]
    if not sounding_blocks:
        raise RuntimeError("Timeline is empty")

    midi = pretty_midi.PrettyMIDI()
    instrument = pretty_midi.Instrument(program=0, name="GestureHarmonyChords")

    tonic_third = 3 if scale_type == "minor" else 4
    chord_map = {
        "ONE": [0, tonic_third, 7],
        "TWO_MINOR": [2, 5, 9],
        "THREE_MINOR": [4, 7, 11],
        "FOUR": [5, 9, 12],
    }

    for idx, block in enumerate(sounding_blocks):
        next_block = sounding_blocks[idx + 1] if idx + 1 < len(sounding_blocks) else None
        note_end = max(block["start"] + 0.01, block["end"])
        pedal_end = next_block["start"] if next_block else note_end

        instrument.control_changes.append(
            pretty_midi.ControlChange(number=64, value=127, time=block["start"])
        )
        instrument.control_changes.append(
            pretty_midi.ControlChange(number=64, value=0, time=max(block["start"] + 0.001, pedal_end))
        )

        intervals = chord_map.get(block["degree"], chord_map["ONE"])
        for interval in intervals:
            note = pretty_midi.Note(
                velocity=96,
                pitch=root_note + interval,
                start=block["start"],
                end=note_end,
            )
            instrument.notes.append(note)

    midi.instruments.append(instrument)
    output_midi = Path(output_midi)
    output_midi.parent.mkdir(parents=True, exist_ok=True)
    midi.write(str(output_midi))

    return output_midi


def render_with_reaper(session_path: Path | str, midi_path: Path | str | None = None) -> Path | None:
    session_path = Path(session_path)
    config = _load_plugin_config()
    reaper_path = config.get("reaper_path") or "reaper"

    source_vocal = session_path / "output.wav"
    if not source_vocal.exists():
        raise FileNotFoundError(f"Missing session vocal file: {source_vocal}")

    if midi_path is None:
        midi_path = session_path / "chords.mid"
    midi_path = Path(midi_path)

    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Missing Reaper template: {TEMPLATE_PATH}")

    # 1. Copy the media files to the template directory
    shutil.copy2(source_vocal, TEMPLATE_VOCAL)
    shutil.copy2(midi_path, TEMPLATE_MIDI)

    # 2. Get the exact duration of the newly recorded audio
    audio_length = librosa.get_duration(path=str(source_vocal))
    
    # 3. Open the master Reaper template as raw text
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        rpp_data = f.read()
        
    # 4. Modify the lengths and loops in memory
    rpp_data = re.sub(r"LENGTH [\d\.]+", f"LENGTH {audio_length}", rpp_data)
    rpp_data = re.sub(r"LOOP 1", "LOOP 0", rpp_data)
    
    # 5. Overwrite the master template IN-PLACE (no temp files created)
    with open(TEMPLATE_PATH, "w", encoding="utf-8") as f:
        f.write(rpp_data)

    # 6. Command Reaper to render the updated master template
    command = [str(reaper_path), "-renderproject", str(TEMPLATE_PATH)]
    try:
        subprocess.run(command, cwd=str(ENGINE_ROOT), check=True)
    except FileNotFoundError:
        print(f"REAPER executable not found at '{reaper_path}'. Please install REAPER or update config/plugin_config.json.")
        return None
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"Reaper render failed with exit code {exc.returncode}") from exc

    if not TEMPLATE_RENDERED.exists():
        raise RuntimeError(f"Reaper render completed but did not produce {TEMPLATE_RENDERED}")

    target = session_path / "harmonized.wav"
    shutil.copy2(TEMPLATE_RENDERED, target)
    return target


def render_session(session_path: Path | str) -> Path | None:
    session_path = Path(session_path)
    timeline = session_path / "timeline.json"
    midi = session_path / "chords.mid"
    source_vocal = session_path / "output.wav"

    if not timeline.exists():
        raise FileNotFoundError(f"Missing session timeline: {timeline}")
    if not source_vocal.exists():
        raise FileNotFoundError(f"Missing session vocal file: {source_vocal}")

    detect_vst_plugin()
    
    # 1. Detect the key from the vocal track
    root_note, scale_type = detect_song_key(source_vocal)
    
    # 2. Pass the detected key into the MIDI generator
    generate_chord_midi(timeline, midi, root_note, scale_type)
    
    # 3. Render
    return render_with_reaper(session_path, midi)


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if not argv:
        print("Usage: python -m engine.vst_renderer <session_path>")
        return 2

    session = Path(argv[0])
    try:
        rendered = render_session(session)
    except Exception as exc:
        print(f"VST render failed: {exc}")
        return 1

    if rendered is None:
        return 1

    print(f"Rendered harmonized audio to {rendered}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())