from __future__ import annotations

import argparse
from pathlib import Path

from engine.vst_renderer import render_session


def run_demo() -> int:
    session = Path("sessions/demo")
    session.mkdir(parents=True, exist_ok=True)

    if not (session / "output.wav").exists() or not (session / "timeline.json").exists():
        print("Demo session requires sessions/demo/output.wav and sessions/demo/timeline.json")
        return 2

    result = render_session(session)
    if result is None:
        return 1
    print(f"Demo render complete: {result}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Gesture Harmony Engine")
    parser.add_argument("--demo", action="store_true", help="Run demo VST render using sessions/demo")
    parser.add_argument("session_path", nargs="?", help="Optional session path to render")
    args = parser.parse_args()

    if args.demo:
        return run_demo()

    if args.session_path:
        result = render_session(Path(args.session_path))
        return 0 if result is not None else 1

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
