#!/bin/sh
set -eu
umask 077

# Run on a disposable PlainNVR OS prototype. Do not modify a live recorder
# without first reviewing this script and the service unit.
if [ "$(id -u)" -ne 0 ] || ! id plainnvr >/dev/null 2>&1; then
    echo 'Run as root on a PlainNVR OS prototype with the plainnvr user.' >&2
    exit 1
fi
if ! mountpoint -q /var/lib/plainnvr || [ ! -f /opt/plainnvr/current/app/server.py ]; then
    echo 'Persistent PlainNVR storage and native runtime are required.' >&2
    exit 1
fi
source_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
driver_dir=/var/lib/plainnvr/drivers/victure
unit_dir=/etc/systemd/system
install -d -m 0700 -o plainnvr -g plainnvr "$driver_dir"
install -m 0644 -o plainnvr -g plainnvr "$source_dir/driver.py" "$driver_dir/driver.py"
if [ ! -e "$driver_dir/token" ]; then
    /usr/bin/python3 -c 'import secrets,sys; open(sys.argv[1],"x").write(secrets.token_urlsafe(48))' "$driver_dir/token"
fi
chown plainnvr:plainnvr "$driver_dir/token"
chmod 0600 "$driver_dir/token"
install -m 0644 "$source_dir/plainnvr-victure-driver.service" "$unit_dir/plainnvr-victure-driver.service"
install -d -m 0755 "$unit_dir/plainnvr.service.d"
printf '%s\n' '[Service]' \
    'Environment=NVR_VICTURE_DRIVER_URL=http://127.0.0.1:8795' \
    'Environment=NVR_VICTURE_DRIVER_TOKEN_FILE=/var/lib/plainnvr/drivers/victure/token' \
    > "$unit_dir/plainnvr.service.d/20-victure-driver.conf"
systemctl daemon-reload
systemctl enable --now plainnvr-victure-driver.service
echo 'Victure driver installed. Review its status, then restart PlainNVR at a chosen maintenance time.'
