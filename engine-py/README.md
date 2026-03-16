# Gesture Harmony Engine

Gesture Harmony Engine now uses an **external VST harmonization pipeline**.
Python handles gesture recognition and timeline/chord logic, while a professional VST plugin renders final harmonized vocals.

## External VST integration

The harmonizer plugin is **not included** due to licensing restrictions.
Install your own plugin, such as:

- Antares Harmony Engine
- Any compatible harmony VST/VST3 plugin

## Setup

1. Install REAPER.
2. Install your harmony VST plugin.
3. Edit `config/plugin_config.json` with your plugin name and REAPER executable path.
4. Configure `templates/harmony_template.rpp` with your plugin routing.

## Pipeline

1. Record vocal (`sessions/<id>/output.wav`).
2. Build gesture timeline (`sessions/<id>/timeline.json`).
3. Generate MIDI chords from inversions.
4. Render harmonized audio through REAPER + VST to `sessions/<id>/harmonized.wav`.

## Demo mode

Run:

```bash
python main.py --demo
```

Demo mode renders `sessions/demo` and exports `sessions/demo/harmonized.wav`.

## Legacy DSP harmonizer

The old internal oscillator harmonizer is preserved for reference at:

`engine/experimental/harmonize_audio_legacy.py`
