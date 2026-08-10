from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import librosa

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


def scale_pitch_classes(ctx: MusicContext) -> list[int]:
    root = ctx.key_semitone()
    intervals = [0, 2, 3, 5, 7, 8, 10] if ctx.scale.lower() == "minor" else [0, 2, 4, 5, 7, 9, 11]
    return [((root + n) % 12) for n in intervals]


def detect_music_context(audio: np.ndarray, sr: int) -> MusicContext:
    if audio.size == 0:
        return MusicContext(key="C", scale="major")

    chroma = librosa.feature.chroma_cqt(y=audio, sr=sr)
    profile = np.mean(chroma, axis=1)
    if not np.isfinite(profile).any():
        return MusicContext(key="C", scale="major")

    major_template = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88], dtype=float)
    minor_template = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17], dtype=float)

    keys = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    best = (float('-inf'), "C", "major")

    for shift, key in enumerate(keys):
        major_score = float(np.dot(profile, np.roll(major_template, shift)))
        if major_score > best[0]:
            best = (major_score, key, "major")

        minor_score = float(np.dot(profile, np.roll(minor_template, shift)))
        if minor_score > best[0]:
            best = (minor_score, key, "minor")

    return MusicContext(key=best[1], scale=best[2])
