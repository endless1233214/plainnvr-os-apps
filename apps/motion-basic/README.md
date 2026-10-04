# Basic Motion

This is a deliberately small reference app. It reads a PlainNVR RTSP
restream, compares down-scaled grayscale frames, and posts `motion` start/stop
events to PlainNVR. It has no camera credentials and no cloud dependency.

Version 0.1.0 is published as
`ghcr.io/endless1233214/plainnvr-motion-basic:0.1.0-df0c8ad6a8d7`.
The manifest pins its immutable GHCR digest. The image is built from a pinned
Python base, runs as an unprivileged user, and needs only CPU and network access.
The release workflow runs unit tests and a disposable integration test against
a PlainNVR go2rtc RTSP restream and the authenticated event endpoint before
publishing a commit-specific tag.

## Configuration

```text
PLAINNVR_URL=http://plainnvr:8787
PLAINNVR_APP_TOKEN=<app token configured on PlainNVR>
PLAINNVR_CAMERA_ID=<camera id>
PLAINNVR_RTSP_URL=rtsp://plainnvr:8554/plainnvr_<camera id>
```

Optional tuning variables are documented in `motion.py`. The app emits events
only; recording, retention, and UI storage remain PlainNVR responsibilities.
