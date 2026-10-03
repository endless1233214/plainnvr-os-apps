# Basic Motion

This is a deliberately small reference app. It reads a PlainNVR RTSP
restream, compares down-scaled grayscale frames, and posts `motion` start/stop
events to PlainNVR. It has no camera credentials and no cloud dependency.

The catalog digest remains a placeholder until the first image is published.
Release automation must replace it with the immutable GHCR digest before the
entry is accepted into the stable catalog.

## Configuration

```text
PLAINNVR_URL=http://plainnvr:8787
PLAINNVR_APP_TOKEN=<app token configured on PlainNVR>
PLAINNVR_CAMERA_ID=<camera id>
PLAINNVR_RTSP_URL=rtsp://plainnvr:8554/plainnvr_<camera id>
```

Optional tuning variables are documented in `motion.py`. The app emits events
only; recording, retention, and UI storage remain PlainNVR responsibilities.
