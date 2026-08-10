import subprocess
import cv2
import numpy as np

def decode_mjpeg_frames(stream, chunk_size=16384):
    buffer = bytearray()
    soi = b"\xff\xd8"
    eoi = b"\xff\xd9"
    while True:
        chunk = stream.read(chunk_size)
        if not chunk:
            break
        buffer.extend(chunk)

        while True:
            start = buffer.find(soi)
            if start < 0:
                if len(buffer) > 2:
                    del buffer[:-2]
                break
            if start > 0:
                del buffer[:start]

            end = buffer.find(eoi, 2)
            if end < 0:
                break

            jpg = bytes(buffer[: end + 2])
            arr = np.frombuffer(jpg, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            del buffer[: end + 2]
            if frame is not None:
                yield frame, False
    yield np.empty((0, 0, 3), dtype=np.uint8), True

cam_name = "HP Wide Vision HD Camera"
mic_name = "Microphone Array (2- Intel® Smart Sound Technology for Digital Microphones)"
cmd = [
    "ffmpeg", "-y", "-f", "dshow", 
    "-i", f"video={cam_name}:audio={mic_name}",
    "-map", "0:v", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
    "-c:a", "aac", "test_video.mp4",
    "-map", "0:v", "-an", "-vf", "fps=30", "-c:v", "mjpeg", "-q:v", "5", "-f", "mjpeg", "pipe:1"
]
print("Running ffmpeg...")
proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

frames_read = 0
for frame, eof in decode_mjpeg_frames(proc.stdout):
    if eof:
        break
    frames_read += 1
    if frames_read > 10:
        break
print(f"Read {frames_read} frames.")
try:
    if proc.stdin:
        proc.stdin.write(b'q\n')
        proc.stdin.flush()
    
    # Drain stdout to prevent deadlock if ffmpeg tries to flush mjpeg pipe
    import threading
    def drain():
        proc.stdout.read()
    t = threading.Thread(target=drain)
    t.start()
    
    proc.wait(timeout=5)
except Exception:
    proc.terminate()
    proc.wait()
