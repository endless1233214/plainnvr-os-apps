# PlainNVR OS Apps

Community catalog for optional PlainNVR applications and camera drivers.

PlainNVR stays useful as a small recorder and viewer. Detection, recognition,
vendor integrations, and other heavyweight features live here as isolated
containers that users can install only when they want them.

## Two kinds of catalog entries

- `kind: app` adds a service such as motion, person, face, vehicle, or audio
  detection. Apps consume a PlainNVR restream and publish typed events back to
  PlainNVR.
- `kind: driver` adds a local camera integration. Drivers may expose discovery,
  controls, and capability metadata through the driver contract without making
  the PlainNVR core depend on a vendor SDK.

Every entry has a manifest, a pinned container image, declared permissions, and
the PlainNVR API contract it needs. Catalog review should reject manifests that
request host networking, privileged mode, Docker socket access, or arbitrary
host mounts unless a driver genuinely requires it and documents why.

## Repository layout

```text
catalog.json                    # signed/reviewed catalog index
schemas/manifest.schema.json    # manifest contract
apps/<name>/manifest.json       # install metadata
apps/<name>/README.md           # user-facing setup and limitations
apps/<name>/compose.yaml        # optional reference compose service
apps/<name>/                    # app source when maintained here
```

## Event contract

An app sends a typed event to `POST /api/apps/events` using its app token:

```json
{
  "camera_id": "camera-id",
  "event_type": "motion",
  "state": "start",
  "confidence": 0.87,
  "source": "plainnvr-motion",
  "metadata": {"mean_delta": 12.4}
}
```

The endpoint is intentionally narrow. Apps do not get database access, camera
passwords, or the Docker socket. PlainNVR owns event retention and the UI.

## Driver contract

Drivers are sidecar services, not Python imports copied into the recorder. A
driver receives a camera host and credentials through its private configuration,
offers capability discovery, and exposes typed operations over the driver API.
The core only enables a driver for cameras whose model/firmware match its
manifest. Secrets must be passed through stdin or a secret file and never put in
URLs, image labels, or logs.

## Security and review

Catalog entries must pin images by digest for releases, declare network and
filesystem permissions, avoid cloud dependencies unless explicitly documented,
and include a license and a reproducible build path. A catalog entry is not
trusted merely because it is present in this repository; installers should
verify the manifest and image digest before starting it.

The catalog and included code are licensed under AGPL-3.0-or-later, except for
third-party components named in their own notices.
