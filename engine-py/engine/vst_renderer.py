from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ENGINE_ROOT = SCRIPT_DIR.parent

PLUGIN_CONFIG_PATH = ENGINE_ROOT / "config" / "plugin_config.json"
TEMPLATE_PATH = ENGINE_ROOT / "templates" / "harmony_template.rpp"
TEMPLATE_VOCAL = ENGINE_ROOT / "templates" / "Media" / "input_vocal-imported.wav"
TEMPLATE_MIDI = ENGINE_ROOT / "templates" / "Media" / "chords.mid"
TEMPLATE_RENDERED = ENGINE_ROOT / "templates" / "harmonized.wav"


try:
    import pretty_midi
except ImportError:  # pragma: no cover
    pretty_midi = None


INVERSION_TO_NOTES = {
    "ROOT": [0, 4, 7],
    "FIRST_INV": [4, 7, 12],
    "THIRD_INV": [7, 12, 16],
}


def normalize_timeline_segments(raw_timeline, min_duration: float = 0.05) -> list[dict]:
    cleaned = []
    for seg in raw_timeline:
        start = float(seg.get("start", 0.0))
        end = float(seg.get("end", start))
        degree = str(seg.get("degree", "ROOT")).upper()

        if degree not in INVERSION_TO_NOTES and degree != "MUTE":
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
        for candidate in root.rglob("*.vst3"):   # ← recursive search
            if target in candidate.stem.lower():
                print(f"Detected VST plugin: {candidate}")
                return True

    print("Harmony Engine VST not found. Please install the plugin.")
    return False


def generate_chord_midi(timeline_path: Path | str, output_midi: Path | str) -> Path:
    if pretty_midi is None:
        raise RuntimeError("pretty_midi is required to generate MIDI chords")

    with Path(timeline_path).open("r", encoding="utf-8") as f:
        raw_timeline = json.load(f)

    blocks = normalize_timeline_segments(raw_timeline)
    if not blocks:
        raise RuntimeError("Timeline is empty")

    midi = pretty_midi.PrettyMIDI()
    instrument = pretty_midi.Instrument(program=0, name="GestureHarmonyChords")
    root = 48  # C3
    legato_bridge_s = 0.03

    for idx, block in enumerate(blocks):
        if block["degree"] == "MUTE":
            continue

        next_block = blocks[idx + 1] if idx + 1 < len(blocks) else None
        note_end = max(block["start"] + 0.01, block["end"])
        if next_block and next_block["degree"] != "MUTE":
            note_end = max(note_end, next_block["start"] + legato_bridge_s)

        intervals = INVERSION_TO_NOTES.get(block["degree"], INVERSION_TO_NOTES["ROOT"])
        for interval in intervals:
            note = pretty_midi.Note(
                velocity=96,
                pitch=root + interval,
                start=block["start"],
                end=note_end,
            )
            instrument.notes.append(note)

    midi.instruments.append(instrument)
    output_midi = Path(output_midi)
    output_midi.parent.mkdir(parents=True, exist_ok=True)
    midi.write(str(output_midi))
    
    return output_midi


def stabilize_timeline(timeline, min_hold=0.25):
    # This acts as a shock absorber. Any gesture held for less than 
    # 0.25 seconds is ignored as a "transition glitch".
    if not timeline:
        return []

    cleaned = []
    for seg in timeline:
        degree = str(seg.get("degree", "ROOT")).upper()
        if degree not in INVERSION_TO_NOTES and degree != "MUTE":
            degree = "MUTE"
        cleaned.append({
            "start": float(seg.get("start", 0.0)),
            "end": float(seg.get("end", 0.0)),
            "degree": degree
        })

    stable = []
    for i, seg in enumerate(cleaned):
        # Check how long this specific gesture lasted
        if i + 1 < len(cleaned):
            duration = cleaned[i+1]["start"] - seg["start"]
            if duration < min_hold:
                continue # Ignore it! The previous chord will just keep holding.
        
        if not stable or stable[-1]["degree"] != seg["degree"]:
            stable.append(seg)

    return stable


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

    shutil.copy2(source_vocal, TEMPLATE_VOCAL)
    shutil.copy2(midi_path, TEMPLATE_MIDI)

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

    if not timeline.exists():
        raise FileNotFoundError(f"Missing session timeline: {timeline}")

    detect_vst_plugin()
    generate_chord_midi(timeline, midi)
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
