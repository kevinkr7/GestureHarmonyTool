from __future__ import annotations

import math
from typing import Iterable


def hz_to_midi(hz: float) -> float:
    if hz <= 0:
        return 0.0
    return 69.0 + 12.0 * math.log2(hz / 440.0)


def build_voice_targets(melody_midi: float, chord_pcs: Iterable[int], voices: int = 4) -> list[float]:
    pcs = list(chord_pcs)
    if not pcs:
        return []

    base_octave = int(melody_midi // 12) * 12
    root = pcs[0]

    bass = max(36, root + base_octave - 12)
    third = min((pcs[1 % len(pcs)] + base_octave), melody_midi + 3)
    fifth = pcs[2 % len(pcs)] + base_octave
    top = fifth + 7 if fifth <= melody_midi else fifth + 12

    stack = [bass, third, fifth, top]
    uniq = sorted(set(stack))
    return uniq[:max(1, min(voices, 4))]
