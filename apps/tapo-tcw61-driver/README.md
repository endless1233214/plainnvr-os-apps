# Tapo TCW61 Local Driver

The first catalog entry for a vendor-specific local driver. The implementation
currently lives in PlainNVR’s `build/tapoctl` helper while the driver contract
and catalog entry are stabilized. It uses the TP-Link account password locally
for TPAP authentication and does not require the Tapo cloud service.

The driver must remain isolated from the recorder process and must not receive
the Docker socket. Camera secrets are supplied through a secret file/stdin and
are never placed in URLs or logs.
