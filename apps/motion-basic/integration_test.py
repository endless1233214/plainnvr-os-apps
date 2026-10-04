#!/usr/bin/env python3
"""Disposable Docker test against PlainNVR's real go2rtc restream and event API.

Run as: python3 integration_test.py. Only containers and a private Docker
network created by this script are removed. No NAS or production containers
are addressed. Random test credentials are never printed.
"""

import http.cookiejar
import json
import os
import secrets
import socket
import subprocess
import time
from urllib import request


MOTION_IMAGE = os.environ.get(
    "MOTION_IMAGE",
    "ghcr.io/endless1233214/plainnvr-motion-basic@sha256:00446c4b6c393f173cd8192e5db3a7db60270bda734084d24992f6fb66cd1843",
)
PLAINNVR_IMAGE = "ghcr.io/endless1233214/plainnvr:0.1.4"
SOURCE_IMAGE = "bluenviron/mediamtx:1.21.1"


def docker(*args, label="Docker command"):
    result = subprocess.run(["docker", *args], text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(f"{label} failed (exit {result.returncode}); inspect disposable container logs locally")
    return result.stdout.strip()


def available_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def until(action, seconds, label):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            result = action()
            if result:
                return result
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
            pass
        time.sleep(1)
    raise RuntimeError(f"Timed out waiting for {label}")


def main():
    suffix = secrets.token_hex(4)
    network = "plainnvr-motion-test-" + suffix
    names = {kind: network + "-" + kind for kind in ("source", "publisher", "nvr", "detector", "probe")}
    token = secrets.token_urlsafe(36)
    password = secrets.token_urlsafe(30)
    port = available_port()
    origin = f"http://127.0.0.1:{port}"
    opener = request.build_opener(request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(path, payload=None):
        body = None if payload is None else json.dumps(payload).encode()
        req = request.Request(origin + path, data=body,
                              headers={"Content-Type": "application/json", "Accept": "application/json"})
        with opener.open(req, timeout=5) as response:
            return json.load(response)

    docker("network", "create", network, label="Create isolated network")
    try:
        docker("run", "-d", "--name", names["source"], "--network", network,
               SOURCE_IMAGE, label="Start synthetic RTSP server")
        time.sleep(2)
        docker("run", "-d", "--name", names["publisher"], "--network", network,
               "--entrypoint", "ffmpeg", MOTION_IMAGE,
               "-hide_banner", "-loglevel", "error", "-re", "-f", "lavfi",
               "-i", "testsrc2=size=320x180:rate=5", "-an", "-vcodec", "libx264",
               "-preset", "ultrafast", "-tune", "zerolatency", "-g", "5", "-f", "rtsp",
               "rtsp://" + names["source"] + ":8554/camera",
               label="Publish synthetic camera")
        time.sleep(2)
        if docker("inspect", "-f", "{{.State.Running}}", names["publisher"]) != "true":
            raise RuntimeError("Synthetic RTSP publisher stopped before PlainNVR connected")
        docker("run", "-d", "--name", names["nvr"], "--network", network,
               "-p", f"127.0.0.1:{port}:8787", "--tmpfs", "/data:uid=568,gid=568,mode=700",
               "--tmpfs", "/recordings:uid=568,gid=568,mode=700",
               "-e", "NVR_APP_TOKEN=" + token, "-e", "NVR_GO2RTC_RTSP_HOST=0.0.0.0",
               PLAINNVR_IMAGE, label="Start isolated PlainNVR")
        until(lambda: call("/api/health").get("ok"), 45, "PlainNVR health")
        call("/api/auth/setup", {"username": "test-admin", "password": password})
        camera = call("/api/cameras", {"name": "Synthetic motion", "record_audio": False,
                                       "rtsp_url": "rtsp://" + names["source"] + ":8554/camera"})
        camera_id = camera["id"]
        restream = f"rtsp://{names['nvr']}:8554/plainnvr_{camera_id}"

        def read_stream(stream):
            try:
                result = subprocess.run(["docker", "run", "--rm", "--name", names["probe"],
                                         "--network", network, "--entrypoint", "ffmpeg", MOTION_IMAGE,
                                         "-hide_banner", "-loglevel", "error", "-rtsp_transport", "tcp",
                                         "-timeout", "5000000", "-i", stream,
                                         "-vframes", "1", "-f", "null", "-"],
                                        capture_output=True, timeout=12)
                return result.returncode == 0
            finally:
                subprocess.run(["docker", "rm", "-f", names["probe"]], capture_output=True)

        until(lambda: read_stream("rtsp://" + names["source"] + ":8554/camera"), 30,
              "synthetic RTSP source")
        print("Synthetic RTSP source decoded successfully")
        until(lambda: read_stream(restream), 45, "PlainNVR RTSP restream")
        print("PlainNVR RTSP restream decoded successfully")
        docker("run", "-d", "--name", names["detector"], "--network", network,
               "-e", "PLAINNVR_URL=http://" + names["nvr"] + ":8787",
               "-e", "PLAINNVR_APP_TOKEN=" + token,
               "-e", "PLAINNVR_CAMERA_ID=" + camera_id,
               "-e", "PLAINNVR_RTSP_URL=" + restream,
               "-e", "MOTION_THRESHOLD=0.5", "-e", "MOTION_START_FRAMES=1",
               MOTION_IMAGE, label="Start motion detector")

        def event_seen(state):
            return any("plainnvr-motion-basic: motion " + state in event.get("message", "")
                       for event in call("/api/status").get("events", []))

        until(lambda: event_seen("start"), 60, "motion start event")
        print("Motion start reached PlainNVR event API")
        docker("stop", "--time", "8", names["detector"], label="Stop motion detector")
        until(lambda: event_seen("stop"), 20, "motion stop event")
        print("Motion stop reached PlainNVR event API")
    finally:
        for name in reversed(list(names.values())):
            subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        subprocess.run(["docker", "network", "rm", network], capture_output=True)


if __name__ == "__main__":
    main()
