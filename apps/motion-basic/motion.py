#!/usr/bin/env python3
"""Small dependency-free motion detector for a PlainNVR restream."""

import json
import os
import signal
import subprocess
import sys
from urllib import request


WIDTH = int(os.environ.get("MOTION_WIDTH", "320"))
HEIGHT = int(os.environ.get("MOTION_HEIGHT", "180"))
FPS = float(os.environ.get("MOTION_FPS", "2"))
THRESHOLD = float(os.environ.get("MOTION_THRESHOLD", "9"))
START_FRAMES = max(1, int(os.environ.get("MOTION_START_FRAMES", "3")))
STOP_FRAMES = max(1, int(os.environ.get("MOTION_STOP_FRAMES", "8")))
SAMPLE_STEP = max(1, int(os.environ.get("MOTION_SAMPLE_STEP", "4")))

running = True


def stop(*_args):
    global running
    running = False


def post_event(state, confidence, mean_delta):
    base = os.environ["PLAINNVR_URL"].rstrip("/")
    payload = {
        "camera_id": os.environ["PLAINNVR_CAMERA_ID"],
        "event_type": "motion",
        "state": state,
        "confidence": max(0.0, min(1.0, confidence)),
        "source": "plainnvr-motion-basic",
        "metadata": {"mean_delta": round(mean_delta, 3)},
    }
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"{base}/api/apps/events",
        data=body,
        headers={
            "Authorization": f"Bearer {os.environ['PLAINNVR_APP_TOKEN']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with request.urlopen(req, timeout=10) as response:
        response.read(4096)


def frames():
    command = [
        "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error",
        "-rtsp_transport", "tcp", "-i", os.environ["PLAINNVR_RTSP_URL"],
        "-vf", f"fps={FPS},scale={WIDTH}:{HEIGHT},format=gray",
        "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1",
    ]
    process = subprocess.Popen(command, stdout=subprocess.PIPE)
    size = WIDTH * HEIGHT
    try:
        while running and process.stdout:
            frame = process.stdout.read(size)
            if len(frame) != size:
                break
            yield frame
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def detect(source, emit=post_event):
    previous = None
    active = False
    above = below = 0
    for frame in source:
        if previous is None:
            previous = frame
            continue
        deltas = (
            abs(frame[index] - previous[index])
            for index in range(0, len(frame), SAMPLE_STEP)
        )
        mean_delta = sum(deltas) / max(1, len(frame) // SAMPLE_STEP)
        previous = frame
        if mean_delta >= THRESHOLD:
            above += 1
            below = 0
            if not active and above >= START_FRAMES:
                try:
                    emit("start", min(1.0, mean_delta / 64.0), mean_delta)
                    active = True
                except OSError as exc:
                    print(f"event delivery failed: {exc}", file=sys.stderr)
        else:
            below += 1
            above = 0
            if active and below >= STOP_FRAMES:
                try:
                    emit("stop", 0.0, mean_delta)
                    active = False
                except OSError as exc:
                    print(f"event delivery failed: {exc}", file=sys.stderr)
    if active:
        try:
            emit("stop", 0.0, 0.0)
        except OSError as exc:
            print(f"event delivery failed: {exc}", file=sys.stderr)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    detect(frames())
