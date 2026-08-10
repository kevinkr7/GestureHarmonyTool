from __future__ import annotations

from pathlib import Path

from engine.vst_renderer import render_session


def process_session(session_path: Path | str):
    """Run the harmony-render stage for an existing session."""
    return render_session(Path(session_path))
