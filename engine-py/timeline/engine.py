from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


@dataclass
class Segment:
    start: float
    end: float
    degree: str


class TimelineEngine:
    def __init__(self, min_segment_s: float = 0.3, stable_ms: float = 200.0):
        self.min_segment_s = min_segment_s
        self.stable_s = stable_ms / 1000.0
        self.segments: list[Segment] = []
        self.current_degree = "ROOT"
        self.current_start = 0.0
        self.pending_degree: str | None = None
        self.pending_since: float = 0.0

    def update(self, degree: str, ts: float) -> None:
        if degree == self.current_degree:
            self.pending_degree = None
            return

        if self.pending_degree != degree:
            self.pending_degree = degree
            self.pending_since = ts
            return

        if ts - self.pending_since < self.stable_s:
            return

        self._close_current(ts)
        self.current_degree = degree
        self.current_start = ts
        self.pending_degree = None

    def finalize(self, end_ts: float) -> list[dict]:
        self._close_current(end_ts)
        merged = []
        for seg in self.segments:
            if seg.end - seg.start < self.min_segment_s:
                continue
            if merged and merged[-1]["degree"] == seg.degree and abs(merged[-1]["end"] - seg.start) < 0.05:
                merged[-1]["end"] = round(seg.end, 3)
                continue
            merged.append({"start": round(seg.start, 3), "end": round(seg.end, 3), "degree": seg.degree})

        if not merged:
            merged = [{"start": 0.0, "end": max(0.5, round(end_ts, 3)), "degree": "ROOT"}]
        return merged

    def write(self, out_path: Path, end_ts: float) -> list[dict]:
        timeline = self.finalize(end_ts)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(timeline, indent=2), encoding="utf-8")
        return timeline

    def _close_current(self, ts: float) -> None:
        if ts <= self.current_start:
            return
        self.segments.append(Segment(self.current_start, ts, self.current_degree))
