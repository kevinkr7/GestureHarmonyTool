from __future__ import annotations

from collections import deque
import math
import mediapipe as mp

mp_hands = mp.solutions.hands
mp_draw = mp.solutions.drawing_utils


class GestureRecognizer:
    def __init__(self, window_size: int = 8):
        self.hands = mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=0.6,
            min_tracking_confidence=0.6,
        )
        self.buffer: deque[str] = deque(maxlen=window_size)

    def close(self) -> None:
        self.hands.close()

    def detect(self, frame) -> str:
        import cv2

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.hands.process(rgb)
        if not results.multi_hand_landmarks:
            return self._smooth("ONE")

        hand = results.multi_hand_landmarks[0]
        mp_draw.draw_landmarks(frame, hand, mp_hands.HAND_CONNECTIONS)

        states = self._finger_states(hand)
        degree = self._map_gesture(states)
        return self._smooth(degree)

    def _smooth(self, degree: str) -> str:
        self.buffer.append(degree)
        return max(set(self.buffer), key=self.buffer.count)

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
