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
        self.current_degree = "ONE"
        self.current_start = 0.0
        self.pending_degree: str | None = None
        self.pending_since: float = 0.0
        self._dirty = True
        self._last_serialized: str | None = None

    @property
    def is_dirty(self) -> bool:
        return self._dirty

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
        self._dirty = True

    def finalize(self, end_ts: float) -> list[dict]:
        merged: list[dict] = []
        for seg in self._iter_all_segments(end_ts):
            start = round(seg.start, 3)
            end = round(seg.end, 3)
            if end - start < self.min_segment_s:
                continue

            if merged and merged[-1]["degree"] == seg.degree and abs(merged[-1]["end"] - start) < 0.05:
                merged[-1]["end"] = end
                continue

            if merged and start < merged[-1]["end"]:
                start = merged[-1]["end"]
                if end - start < self.min_segment_s:
                    continue

            merged.append({"start": start, "end": end, "degree": seg.degree})

        if not merged:
            merged = [{"start": 0.0, "end": max(0.5, round(end_ts, 3)), "degree": "ONE"}]
        return merged

    def write(self, out_path: Path, end_ts: float, *, pretty: bool = True, force: bool = False) -> list[dict]:
        timeline = self.finalize(end_ts)
        serialized = json.dumps(timeline, indent=2 if pretty else None)
        if not force and not self._dirty and serialized == self._last_serialized:
            return timeline

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(serialized, encoding="utf-8")
        self._dirty = False
        self._last_serialized = serialized
        return timeline

    def _close_current(self, ts: float) -> None:
        if ts <= self.current_start:
            return
        self.segments.append(Segment(self.current_start, ts, self.current_degree))

    def _iter_all_segments(self, end_ts: float) -> list[Segment]:
        timeline: list[Segment] = []
        for seg in self.segments:
            if seg.start >= end_ts:
                continue
            timeline.append(Segment(seg.start, min(seg.end, end_ts), seg.degree))

        effective_end = max(end_ts, self.current_start)
        if effective_end > self.current_start and self.current_start < end_ts:
            timeline.append(Segment(self.current_start, end_ts, self.current_degree))

        timeline.sort(key=lambda seg: (seg.start, seg.end))
        return timeline
