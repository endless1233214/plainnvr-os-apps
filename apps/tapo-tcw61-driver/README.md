# Tapo TCW61 Local Driver

This is a real PlainNVR driver sidecar, not a cloud adapter. It exposes the
`plainnvr-driver-v1` HTTP contract and uses the same pinned `plainnvr-tapoctl`
helper as the PlainNVR core for local TPAP/SPAKE2+ authentication.

It supports:

- capability discovery for TCW61 cameras;
- read-only probe and state requests; and
- spotlight, privacy mask, status LED, night vision, siren, audio volume, and
  reboot controls when the camera firmware supports them.

## Endpoints

Set `DRIVER_TOKEN` and send it as `Authorization: Bearer <token>`.

```text
GET  /health
GET  /v1/capabilities
POST /v1/probe
POST /v1/state
POST /v1/control
```

Probe/state requests contain `host`, `username`, and `password`. Control adds
`control` and `value`. Credentials are accepted only in the request body,
passed to the helper over stdin, and never logged or put in URLs.

The sidecar allows only local/private camera IPs, runs without host mounts,
devices, privileges, or the Docker socket, and serializes requests per camera.
Use the compose example as a reference and attach its network to both the
PlainNVR service and the camera LAN.
