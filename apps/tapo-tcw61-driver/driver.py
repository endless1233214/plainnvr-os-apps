#!/usr/bin/env python3
"""Small, dependency-free PlainNVR driver sidecar for Tapo TCW61 cameras.

The sidecar owns the vendor protocol boundary.  It accepts camera credentials
only in a request body, forwards the request to the pinned plainnvr-tapoctl
helper over stdin, and never logs request bodies or helper output.
"""

import ipaddress
import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


VERSION = "0.1.0"
PROTOCOL = "plainnvr-driver-v1"
MAX_BODY = 64 << 10
MAX_OUTPUT = 2 << 20
CONTROLS = frozenset(
    {
        "spotlight",
        "spotlight_intensity",
        "privacy",
        "led",
        "night_vision",
        "siren",
        "microphone_volume",
        "speaker_volume",
        "reboot",
    }
)

_locks_guard = threading.Lock()
_locks = {}


class DriverError(ValueError):
    """A safe, client-visible driver error."""


def _lock_for(host):
    with _locks_guard:
        return _locks.setdefault(host, threading.Lock())


def _local_ip(value):
    try:
        address = ipaddress.ip_address(str(value or "").strip())
    except ValueError as exc:
        raise DriverError("host must be a local IP address") from exc
    if (
        not (address.is_private or address.is_loopback or address.is_link_local)
        or address.is_multicast
        or address.is_unspecified
    ):
        raise DriverError("host must be a local IP address")
    return str(address)


def _secret(value, name, limit):
    if not isinstance(value, str) or not value or len(value) > limit:
        raise DriverError(f"{name} is missing or invalid")
    return value


def _request_credentials(payload):
    if not isinstance(payload, dict):
        raise DriverError("request must be a JSON object")
    host = _local_ip(payload.get("host"))
    username = _secret(payload.get("username"), "username", 320)
    password = _secret(payload.get("password"), "password", 1024)
    return host, username, password


def _redact(message, username, password):
    text = str(message)
    for secret in (username, password):
        if secret:
            text = text.replace(secret, "<redacted>")
    return text[:500]


def invoke(payload, operation, control=None, value=None):
    host, username, password = _request_credentials(payload)
    if operation == "set":
        if control not in CONTROLS:
            raise DriverError("unsupported Tapo control")
    request = {
        "host": host,
        "username": username,
        "password": password,
        "operation": operation,
    }
    if operation == "set":
        request["control"] = control
        request["value"] = value
    helper = os.environ.get("TAPOCTL_BIN", "/usr/local/bin/plainnvr-tapoctl")
    timeout = float(os.environ.get("DRIVER_HELPER_TIMEOUT", "15"))
    try:
        with _lock_for(host):
            result = subprocess.run(
                [helper],
                input=json.dumps(request, separators=(",", ":")).encode(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                check=False,
            )
    except FileNotFoundError as exc:
        raise DriverError("Tapo helper is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise DriverError("Tapo camera request timed out") from exc
    if len(result.stdout) > MAX_OUTPUT or len(result.stderr) > MAX_OUTPUT:
        raise DriverError("Tapo helper returned too much data")
    try:
        response = json.loads(result.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DriverError("Tapo helper returned invalid JSON") from exc
    if not isinstance(response, dict):
        raise DriverError("Tapo helper returned an invalid response")
    if result.returncode != 0 or not response.get("ok"):
        raise DriverError(
            _redact(response.get("error") or "camera rejected request", username, password)
        )
    return response


def _token_valid(handler):
    expected = os.environ.get("DRIVER_TOKEN", "")
    if not expected:
        return True
    supplied = handler.headers.get("Authorization", "")
    return supplied == f"Bearer {expected}"


class Handler(BaseHTTPRequestHandler):
    server_version = "PlainNVR-TapoDriver/" + VERSION

    def log_message(self, _format, *_args):
        # Do not log request paths or headers; future protocol additions may
        # carry sensitive values.
        return

    def _send(self, status, body):
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "-1"))
        except ValueError as exc:
            raise DriverError("invalid request length") from exc
        if length < 0 or length > MAX_BODY:
            raise DriverError("request body is too large")
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DriverError("request body must be valid JSON") from exc

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"ok": True, "driver": "tapo-tcw61", "version": VERSION})
            return
        if self.path == "/v1/capabilities":
            if not _token_valid(self):
                self._send(401, {"ok": False, "error": "unauthorized"})
                return
            self._send(
                200,
                {
                    "ok": True,
                    "protocol": PROTOCOL,
                    "driver": "tapo-tcw61",
                    "camera_models": ["TP-Link Tapo TCW61"],
                    "operations": ["probe", "state", "set"],
                    "controls": sorted(CONTROLS),
                },
            )
            return
        self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        if not _token_valid(self):
            self._send(401, {"ok": False, "error": "unauthorized"})
            return
        routes = {
            "/v1/probe": ("probe", None),
            "/v1/state": ("state", None),
            "/v1/control": ("set", True),
        }
        route = routes.get(self.path)
        if route is None:
            self._send(404, {"ok": False, "error": "not found"})
            return
        try:
            payload = self._read_json()
            operation, needs_control = route
            control = payload.get("control") if needs_control else None
            value = payload.get("value") if needs_control else None
            result = invoke(payload, operation, control, value)
            self._send(200, result)
        except DriverError as exc:
            self._send(400, {"ok": False, "error": str(exc)})
        except Exception:
            self._send(500, {"ok": False, "error": "driver request failed"})


def main():
    bind = os.environ.get("DRIVER_BIND", "127.0.0.1")
    port = int(os.environ.get("DRIVER_PORT", "8789"))
    if bind not in ("127.0.0.1", "::1", "localhost") and not os.environ.get("DRIVER_TOKEN"):
        raise SystemExit("DRIVER_TOKEN is required when the driver is not loopback-only")
    server = ThreadingHTTPServer((bind, port), Handler)
    server.daemon_threads = True
    server.serve_forever()


if __name__ == "__main__":
    main()
