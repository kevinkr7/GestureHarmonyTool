from __future__ import annotations

from dataclasses import dataclass

KEY_TO_SEMITONE = {
    "C": 0, "B#": 0, "C#": 1, "DB": 1, "D": 2, "D#": 3, "EB": 3,
    "E": 4, "FB": 4, "F": 5, "E#": 5, "F#": 6, "GB": 6, "G": 7,
    "G#": 8, "AB": 8, "A": 9, "A#": 10, "BB": 10, "B": 11, "CB": 11,
}

MAJOR_SCALE_DEGREES = {
    "I": [0, 4, 7],
    "II": [2, 5, 9],
    "III": [4, 7, 11],
    "IV": [5, 9, 0],
    "V": [7, 11, 2],
    "VI": [9, 0, 4],
    "VII": [11, 2, 5],
}

MINOR_SCALE_DEGREES = {
    "I": [0, 3, 7],
    "II": [2, 5, 8],
    "III": [3, 7, 10],
    "IV": [5, 8, 0],
    "V": [7, 10, 2],
    "VI": [8, 0, 3],
    "VII": [10, 2, 5],
}


@dataclass(frozen=True)
class MusicContext:
    key: str
    scale: str

    def key_semitone(self) -> int:
        return KEY_TO_SEMITONE.get(self.key.upper().replace("♯", "#").replace("♭", "B"), 0)


def chord_pitch_classes(ctx: MusicContext, degree: str) -> list[int]:
    degree_key = degree.strip().upper()
    table = MINOR_SCALE_DEGREES if ctx.scale.lower() == "minor" else MAJOR_SCALE_DEGREES
    rel = table.get(degree_key, table["I"])
    root = ctx.key_semitone()
    return [((root + n) % 12) for n in rel]
