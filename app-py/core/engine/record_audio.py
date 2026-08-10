"""Audio recording hooks for session workflows.

This module is intentionally lightweight in this refactor; UI/front-end layers
own recording in the current application.
"""

from __future__ import annotations

from pathlib import Path


def session_output_path(session_path: Path | str) -> Path:
    return Path(session_path) / "output.wav"
