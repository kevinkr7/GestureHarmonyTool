from flask import Flask, Response
import cv2
import mediapipe as mp

app = Flask(__name__)

# ----------------------------
# Camera Setup
# ----------------------------

cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

mpHands = mp.solutions.hands
mpDraw = mp.solutions.drawing_utils

hands = mpHands.Hands(
    static_image_mode=False,
    max_num_hands=1,
    min_detection_confidence=0.6,
    min_tracking_confidence=0.6
)

current_chord = "NONE"

def chord_from_fingers(f):
    if f == 1: return "I"
    if f == 2: return "IV"
    if f == 3: return "V"
    return "NONE"

# ----------------------------
# Frame Generator
# ----------------------------

def generate_frames():
    global current_chord

    while True:
        success, frame = cap.read()
        if not success:
            break

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = hands.process(rgb)

        raw = "NONE"

        if results.multi_hand_landmarks:
            lms = results.multi_hand_landmarks[0]
            mpDraw.draw_landmarks(frame, lms, mpHands.HAND_CONNECTIONS)

            def up(tip, pip):
                return lms.landmark[tip].y < lms.landmark[pip].y

            fingers = (
                up(8, 6) +
                up(12, 10) +
                up(16, 14) +
                up(20, 18)
            )

            raw = chord_from_fingers(fingers)

        current_chord = raw

        # Overlay text
        cv2.rectangle(frame, (20, 20), (350, 100), (0, 0, 0), -1)
        cv2.putText(
            frame,
            f"Chord: {current_chord}",
            (40, 75),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.2,
            (0, 255, 0),
            3
        )

        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

# ----------------------------
# Flask Route
# ----------------------------

@app.route('/video')
def video():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

# ----------------------------

if __name__ == "__main__":
    app.run(host='127.0.0.1', port=5000, threaded=True)