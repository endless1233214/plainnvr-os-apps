# Optional Victure driver

This service carries both existing Victure control modes out of the PlainNVR
recorder process: `victure_dvrip` (PTZ and camera clock) and `victure_direct`
(directional step commands). It is CPU-only, local-only, and uses only Python's
standard library. The recorder's existing camera settings are retained.

The driver accepts commands only with a shared bearer token and only targets
literal RFC 1918 or IPv6 ULA camera addresses. It must never be exposed on a
public port. Camera credentials stay in the authenticated request body; neither
the service nor the recorder logs the body. There is no cloud dependency.

## Standalone Docker / TrueNAS sandbox

Create a random token of at least 32 characters in a private file readable by
the recorder and driver. Attach both services to the same private Docker
network. `compose.yaml` is a reference service: it has no published port,
drops capabilities, runs as a non-root user, and mounts only the token secret.
Configure the recorder with:

```text
NVR_VICTURE_DRIVER_URL=http://victure-driver:8795
NVR_VICTURE_DRIVER_TOKEN_FILE=/run/secrets/victure_driver_token
```

Do not add the driver to a production TrueNAS installation before testing the
image and the network/secret wiring in the sandbox. The reference Compose file
is not a TrueNAS catalog app and is not an automatic installer.

## PlainNVR OS prototype

PlainNVR OS is a native Debian runtime, not a container host. On a disposable
test instance, review and run `install-native.sh` as root. It installs the
driver code on persistent storage, creates a private random token, installs a
systemd unit and recorder drop-in, and starts only the new driver. It does
**not** restart the recorder; do that separately at a chosen maintenance time.
The installed recorder drop-in contains:

```text
NVR_VICTURE_DRIVER_URL=http://127.0.0.1:8795
NVR_VICTURE_DRIVER_TOKEN_FILE=/var/lib/plainnvr/drivers/victure/token
```

The OS prototype does not yet have an app/driver installer or an upgrade-safe
unit lifecycle. This is a manual, test-only install path; do not distribute it
as a one-click OS package yet.

## Compatibility and migration

In an existing installation the in-process Victure path remains active until
`NVR_VICTURE_DRIVER_URL` is set. Once it is set, driver errors are reported
instead of silently falling back to in-process control. This avoids sending
commands by a path the operator thought was disabled. A DVRIP camera must have
its own passhash in the camera's PTZ credential field or explicit control URL;
the external driver intentionally does not carry a vendor default credential.
Camera IPs must be private literals, not DNS names. If your cameras use names,
assign static DHCP leases and enter the private IPs before migration.
