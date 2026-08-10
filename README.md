# 🎵 GestureHarmony

> **Bridging passion and profession through music and technology.**

GestureHarmony is a Python-based computer vision and music interaction tool that maps hand gestures to musical chords, generates MIDI events, and produces real-time harmonized output.

## ✨ How It Works

```text
Hand Gesture
     ↓
Gesture Recognition
     ↓
Gesture → Chord Mapping
     ↓
MIDI Chord Generation
     ↓
VST-Based Harmonization
     ↓
Musical Output
```

The goal is to explore how natural hand gestures can become an expressive interface for musical performance.

## 📁 Project Structure

```text
GestureHarmony/
├── engine-py/      # Core Python engine and VST harmonization
├── app-py/         # Python GUI and live gesture interaction
├── app-java/       # Java UI alternative
├── docs/           # Project documentation
├── sessions/       # Session data (ignored by Git)
└── README.md
```

## 🛠️ Built With

- **Python** — core engine and primary application
- **Java** — alternative UI
- **Computer Vision** — hand gesture recognition
- **MIDI** — chord and musical event generation
- **VST Architecture** — real-time harmonization

## 🚀 Getting Started

### Python Application

```bash
cd app-py
pip install -r requirements.txt
python main.py
```

### Core Engine

```bash
cd engine-py
pip install -r requirements.txt
```

See [`engine-py/README.md`](engine-py/README.md) for VST-specific setup.

## 🎼 Example

Different hand gestures can be mapped to different chords:

```text
Gesture 1 → Chord 1
Gesture 2 → Chord 2
Gesture 3 → Chord 3
Gesture 4 → Chord 4
```

This allows a performer to control harmony using hand gestures instead of a traditional MIDI controller.

## 🎥 Demo

A live demonstration of GestureHarmony is available on LinkedIn:

👉 [Watch the GestureHarmony Demo](https://www.linkedin.com/posts/kevinkr77_python-computervision-opencv-activity-7491130652797444096-Qxao)

The demo showcases real-time hand gesture recognition, gesture-to-chord mapping, MIDI-based harmony generation, and live vocal harmonization.


## 📌 Notes

Generated videos, temporary files, compiled binaries, and session data are excluded from version control through `.gitignore`.

---

### 🎵 GestureHarmony

**Turn gestures into harmony.**
