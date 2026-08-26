/**
 * Harmonza — simulated engine layer.
 *
 * Everything in this file is a FRONTEND SIMULATION used for the showcase.
 * It is intentionally isolated behind a small interface so it can later be
 * swapped for a real Python backend (REST / WebSocket) without touching UI code:
 *
 *   const engine: HarmonzaEngine = createSimulatedEngine();
 *   // later: createWebSocketEngine("wss://.../harmonza")
 */

export type GestureId = "gesture-1" | "gesture-2" | "gesture-3" | "gesture-4";

export interface GestureState {
  id: GestureId;
  index: number;
  label: string;
  /** Human readable description of the hand pose. */
  pose: string;
  chord: string;
  quality: string;
  /** MIDI note numbers sent to the harmonization engine. */
  midi: number[];
  /** Note names for display. */
  notes: string[];
  /** Fingers extended, index 0 = thumb. Drives the hand visual. */
  fingers: [boolean, boolean, boolean, boolean, boolean];
  /** Base frequency multiplier used by the waveform visual. */
  timbre: number;
  harmonyLabel: string;
}

export const GESTURES: GestureState[] = [
  {
    id: "gesture-1",
    index: 1,
    label: "Gesture 1",
    pose: "Open palm",
    chord: "C Major",
    quality: "Bright · Root position",
    midi: [60, 64, 67, 72],
    notes: ["C4", "E4", "G4", "C5"],
    fingers: [true, true, true, true, true],
    timbre: 1,
    harmonyLabel: "Harmony Active",
  },
  {
    id: "gesture-2",
    index: 2,
    label: "Gesture 2",
    pose: "Two fingers raised",
    chord: "G# Major",
    quality: "Lifted · First inversion",
    midi: [68, 72, 75, 80],
    notes: ["G#4", "C5", "D#5", "G#5"],
    fingers: [false, true, true, false, false],
    timbre: 1.34,
    harmonyLabel: "Harmony Active",
  },
  {
    id: "gesture-3",
    index: 3,
    label: "Gesture 3",
    pose: "Pinch",
    chord: "A Minor 7",
    quality: "Warm · Suspended tension",
    midi: [57, 60, 64, 67],
    notes: ["A3", "C4", "E4", "G4"],
    fingers: [true, true, false, false, false],
    timbre: 0.78,
    harmonyLabel: "Harmony Active",
  },
  {
    id: "gesture-4",
    index: 4,
    label: "Gesture 4",
    pose: "Closed fist",
    chord: "F Major 9",
    quality: "Wide · Extended voicing",
    midi: [53, 57, 60, 67],
    notes: ["F3", "A3", "C4", "G4"],
    fingers: [false, false, false, false, false],
    timbre: 0.58,
    harmonyLabel: "Harmony Active",
  },
];

export interface HarmonzaEngine {
  /** All gestures the engine can recognise. */
  gestures(): GestureState[];
  /** Resolve a gesture id into its harmonic state. */
  resolve(id: GestureId): GestureState;
  /** Subscribe to engine-emitted gesture changes (real engine: camera frames). */
  subscribe(listener: (state: GestureState) => void): () => void;
}

export function createSimulatedEngine(): HarmonzaEngine {
  const listeners = new Set<(state: GestureState) => void>();
  return {
    gestures: () => GESTURES,
    resolve: (id) => GESTURES.find((g) => g.id === id) ?? GESTURES[0]!,
    subscribe: (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}

export const harmonzaEngine = createSimulatedEngine();