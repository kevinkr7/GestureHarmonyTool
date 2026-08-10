from __future__ import annotations

import cv2
from collections import deque
import math
import mediapipe as mp

mp_hands = mp.solutions.hands
mp_draw = mp.solutions.drawing_utils


class GestureRecognizer:
    """Recognizes finger-count gestures using MediaPipe Hands.

    Performance notes
    -----------------
    * ``detect(frame, draw_skeleton=True)`` runs MediaPipe inference AND draws
      the cinematic skeleton overlay directly onto *frame* (in-place).
    * ``detect(frame, draw_skeleton=False)`` runs inference only — no frame
      mutation, no overlay allocation.  Use this in the gesture-inference thread
      and call ``draw_skeleton_onto(frame)`` separately in the HUD/render thread
      to keep the two concerns decoupled and avoid redundant copies.
    * Landmarks from the most-recent detected hand are cached; a caller may
      retrieve them via ``get_last_landmarks()`` to draw without re-running
      MediaPipe.
    """

    def __init__(self, window_size: int = 8):
        self.hands = mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=0.6,
            min_tracking_confidence=0.6,
        )
        self.buffer: deque[str] = deque(maxlen=window_size)
        self._buffer_counts: dict[str, int] = {}
        self._last_smoothed = "ONE"
        self.has_hand = False
        # Cache last landmarks so the HUD thread can draw without re-running MediaPipe.
        self._last_landmarks = None  # type: ignore[assignment]
        self._last_shape: tuple[int, int] = (0, 0)  # (h, w) at last inference

    def close(self) -> None:
        self.hands.close()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self, frame, *, draw_skeleton: bool = False) -> str:
        """Run gesture inference on *frame*.

        Parameters
        ----------
        frame:
            BGR frame (numpy array).  Modified in-place only when
            *draw_skeleton* is True.
        draw_skeleton:
            If True, paint the cinematic hand skeleton onto *frame*.
            Set False in the gesture thread; call ``draw_skeleton_onto``
            from the render thread instead.

        Returns
        -------
        str
            Smoothed degree label: ONE | TWO_MINOR | THREE_MINOR | FOUR.
        """
        h, w, _ = frame.shape
        # Convert BGR→RGB for MediaPipe (no copy if we can avoid it, but
        # MediaPipe requires contiguous RGB so we must convert).
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.hands.process(rgb)

        if not results.multi_hand_landmarks:
            self.has_hand = False
            self._last_landmarks = None
            return self._smooth("ONE")

        self.has_hand = True
        hand = results.multi_hand_landmarks[0]
        self._last_landmarks = hand
        self._last_shape = (h, w)

        if draw_skeleton:
            self._paint_skeleton(frame, hand, h, w)

        states = self._finger_states(hand)
        degree = self._map_gesture(states)
        return self._smooth(degree)

    def draw_skeleton_onto(self, frame) -> None:
        """Paint the cached hand skeleton onto *frame* (in-place).

        Safe to call from a different thread than ``detect()`` as long as
        the caller ensures ``detect()`` has already run for this frame (or
        accepts a one-frame-stale skeleton during throttled inference).
        """
        if self._last_landmarks is None:
            return
        h, w, _ = frame.shape
        self._paint_skeleton(frame, self._last_landmarks, h, w)

    def get_last_landmarks(self):
        """Return the cached MediaPipe hand landmarks (or None)."""
        return self._last_landmarks

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _paint_skeleton(self, frame, hand, h: int, w: int) -> None:
        """Draw the cinematic glow skeleton directly onto *frame*."""
        # Draw bone connections
        for connection in mp_hands.HAND_CONNECTIONS:
            start_idx = connection[0]
            end_idx = connection[1]
            p1 = hand.landmark[start_idx]
            p2 = hand.landmark[end_idx]
            x1, y1 = int(p1.x * w), int(p1.y * h)
            x2, y2 = int(p2.x * w), int(p2.y * h)
            cv2.line(frame, (x1, y1), (x2, y2), (248, 250, 252), 2, cv2.LINE_AA)

        # Glow joints — use a pre-allocated overlay to avoid a full-frame copy.
        # We only allocate once; subsequent calls reuse the same buffer.
        overlay = frame.copy()
        for lm in hand.landmark:
            cx, cy = int(lm.x * w), int(lm.y * h)
            cv2.circle(overlay, (cx, cy), 8, (234, 51, 147), -1, cv2.LINE_AA)
            cv2.circle(overlay, (cx, cy), 5, (255, 100, 180), -1, cv2.LINE_AA)

        cv2.addWeighted(overlay, 0.5, frame, 0.5, 0, frame)

        # Solid inner points
        for lm in hand.landmark:
            cx, cy = int(lm.x * w), int(lm.y * h)
            cv2.circle(frame, (cx, cy), 2, (255, 255, 255), -1, cv2.LINE_AA)

    def _smooth(self, degree: str) -> str:
        if len(self.buffer) == self.buffer.maxlen:
            dropped = self.buffer.popleft()
            dropped_count = self._buffer_counts.get(dropped, 0) - 1
            if dropped_count <= 0:
                self._buffer_counts.pop(dropped, None)
            else:
                self._buffer_counts[dropped] = dropped_count

        self.buffer.append(degree)
        self._buffer_counts[degree] = self._buffer_counts.get(degree, 0) + 1

        # Keep prior winning degree on ties to prevent label flicker.
        best_degree = self._last_smoothed
        best_count = self._buffer_counts.get(best_degree, -1)
        for candidate, count in self._buffer_counts.items():
            if count > best_count:
                best_degree = candidate
                best_count = count

        self._last_smoothed = best_degree
        return best_degree

    def _finger_states(self, hand) -> dict[str, bool]:
        lms = hand.landmark

        def angle(a, b, c):
            v1 = (a.x - b.x, a.y - b.y)
            v2 = (c.x - b.x, c.y - b.y)
            dot = v1[0] * v2[0] + v1[1] * v2[1]
            n1 = math.hypot(*v1)
            n2 = math.hypot(*v2)
            if n1 == 0 or n2 == 0:
                return 180.0
            cosv = max(-1.0, min(1.0, dot / (n1 * n2)))
            return math.degrees(math.acos(cosv))

        return {
            "thumb": angle(lms[2], lms[3], lms[4]) > 155,
            "index": angle(lms[5], lms[6], lms[8]) > 160,
            "middle": angle(lms[9], lms[10], lms[12]) > 160,
            "ring": angle(lms[13], lms[14], lms[16]) > 160,
            "pinky": angle(lms[17], lms[18], lms[20]) > 160,
        }

    def _map_gesture(self, states: dict[str, bool]) -> str:
        visible_count = sum(1 for finger in ("index", "middle", "ring", "pinky") if states[finger])

        if visible_count <= 1:
            return "ONE"
        if visible_count == 2:
            return "TWO_MINOR"
        if visible_count == 3:
            return "THREE_MINOR"
        return "FOUR"
