"""Optional local Victure PTZ/clock driver; no cloud or third-party packages."""

import hmac
import http.client
import ipaddress
import json
import os
import socket
import struct
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlencode, urlparse


HEADER = struct.Struct("<BBHIIBBHI")
COMMANDS = {
    "up": "DirectionUp", "down": "DirectionDown", "left": "DirectionLeft",
    "right": "DirectionRight", "up_left": "DirectionLeftUp",
    "up_right": "DirectionRightUp", "down_left": "DirectionLeftDown",
    "down_right": "DirectionRightDown", "zoom_in": "ZoomTile",
    "zoom_out": "ZoomWide", "stop": "Stop",
}
DIRECTIONS = frozenset(COMMANDS) - {"zoom_in", "zoom_out", "stop"}


def private_ip(host):
    """Only literal, private camera IPs; avoids DNS rebinding and public targets."""
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ValueError("Camera endpoint must use a private IP address.") from exc
    allowed = (ipaddress.ip_network("10.0.0.0/8"),
               ipaddress.ip_network("172.16.0.0/12"),
               ipaddress.ip_network("192.168.0.0/16"),
               ipaddress.ip_network("fc00::/7"))
    if not any(address in subnet for subnet in allowed):
        raise ValueError("Camera endpoint must use a private IP address.")
    return str(address)


def target(camera, mode):
    explicit = str(camera.get("ptz_url") or "").strip()
    source = explicit or str(camera.get("rtsp_url") or "").strip()
    if not source:
        raise ValueError("Camera control endpoint is missing.")
    if explicit and "://" not in source:
        source = ("dvrip://" if mode == "victure_dvrip" else "http://") + source
    parsed = urlparse(source)
    host = private_ip(parsed.hostname or "")
    port = parsed.port if explicit and parsed.port else (34567 if mode == "victure_dvrip" else 8088)
    if mode == "victure_direct":
        scheme = parsed.scheme if explicit and parsed.scheme in ("http", "https") else "http"
        return host, port, scheme, None, None
    if mode != "victure_dvrip":
        raise ValueError("Unsupported Victure mode.")
    username = unquote(parsed.username) if explicit and parsed.username else "admin"
    passhash = unquote(parsed.password) if explicit and parsed.password else str(camera.get("ptz_profile_token") or "")
    if not passhash or passhash == "Profile_1":
        raise ValueError("DVRIP credential must be configured for the external driver.")
    return host, port, "dvrip", username, passhash


def receive_exact(connection, length):
    chunks = []
    while length:
        part = connection.recv(length)
        if not part:
            raise RuntimeError("Camera closed its DVRIP connection.")
        chunks.append(part)
        length -= len(part)
    return b"".join(chunks)


def packet(connection, session, number, kind, data):
    payload = json.dumps(data, separators=(",", ":")).encode("utf-8")
    connection.sendall(HEADER.pack(255, 1, 0, session, number, 0, 0, kind, len(payload)) + payload)


def response(connection):
    magic, version, _, _, _, _, _, _, length = HEADER.unpack(receive_exact(connection, HEADER.size))
    if (magic, version) != (255, 1) or length > 65536:
        raise RuntimeError("Invalid DVRIP response header.")
    return json.loads(receive_exact(connection, length).rstrip(b"\0"))


def login(connection, username, passhash):
    packet(connection, 0, 2, 1000, {
        "EncryptType": "MD5", "LoginType": "DVRIP-Web",
        "UserName": username, "PassWord": passhash,
    })
    result = response(connection)
    session_id = result.get("SessionID", 0)
    session = int(session_id, 0) if isinstance(session_id, str) else int(session_id)
    if result.get("Ret") != 100 or not session:
        raise RuntimeError("DVRIP login failed.")
    return session


def ptz_payload(session, command, preset, step):
    return {"Name": "OPPTZControl", "SessionID": f"0x{session:08X}",
            "OPPTZControl": {"Command": command, "Parameter": {
                "AUX": {"Number": 0, "Status": "On"}, "Channel": 0,
                "MenuOpts": "Enter", "POINT": {"bottom": 0, "left": 0, "right": 0, "top": 0},
                "Pattern": "SetBegin", "Preset": preset, "Step": step, "Tour": 0,
            }}}


def dvrip_ptz(camera, action, speed, duration_ms):
    if action == "home":
        return {"ok": True, "driver": "victure_dvrip", "action": action,
                "warning": "Home is not available on the Victure DVRIP driver."}
    if action not in COMMANDS:
        raise ValueError("Unsupported PTZ action.")
    host, port, _, username, passhash = target(camera, "victure_dvrip")
    step = max(1, min(64, round(speed * 4)))
    with socket.create_connection((host, port), timeout=4) as connection:
        connection.settimeout(4)
        session = login(connection, username, passhash)
        if action == "stop":
            for index, command in enumerate(("DirectionUp", "DirectionDown", "DirectionLeft", "DirectionRight")):
                packet(connection, session, 4 + index, 1400, ptz_payload(session, command, -1, step))
        else:
            command = COMMANDS[action]
            packet(connection, session, 4, 1400, ptz_payload(session, command, 65535, step))
            time.sleep(duration_ms / 1000)
            packet(connection, session, 5, 1400, ptz_payload(session, command, -1, step))
    return {"ok": True, "driver": "victure_dvrip", "action": action,
            "step": step, "duration_ms": duration_ms if action in DIRECTIONS else 0}


def direct_ptz(camera, action, speed):
    if action not in DIRECTIONS:
        return {"ok": True, "driver": "victure_direct", "action": action,
                "warning": "This Victure direct-step driver only supports directional moves."}
    host, port, scheme, _, _ = target(camera, "victure_direct")
    step = max(1, min(256, round(speed * 64)))
    connection_type = http.client.HTTPSConnection if scheme == "https" else http.client.HTTPConnection
    connection = connection_type(host, port, timeout=4)
    try:
        connection.request("POST", "/ptz", urlencode({"action": action, "step": step}),
                           {"Content-Type": "application/x-www-form-urlencoded"})
        reply = connection.getresponse()
        reply.read(2048)
        status = reply.status
    finally:
        connection.close()
    if status >= 400:
        raise RuntimeError("Victure direct-step command failed.")
    return {"ok": True, "driver": "victure_direct", "action": action,
            "step": step, "status": status}


def camera_time(camera, requested):
    if not camera.get("time_sync_supported"):
        raise ValueError("Clock sync is not available for this camera driver.")
    target_camera = dict(camera)
    if camera.get("ptz_type") != "victure_dvrip":
        target_camera["ptz_url"] = ""
    host, port, _, username, passhash = target(target_camera, "victure_dvrip")
    with socket.create_connection((host, port), timeout=4) as connection:
        connection.settimeout(4)
        session = login(connection, username, passhash)
        number = 4
        if requested is not None:
            value = datetime.fromisoformat(str(requested).replace("Z", "+00:00")) if requested else datetime.now()
            value = value.astimezone().replace(tzinfo=None, microsecond=0) if value.tzinfo else value.replace(microsecond=0)
            if not 2001 <= value.year <= 2100:
                raise ValueError("Camera date must be between 2001 and 2100.")
            packet(connection, session, 4, 1450, {"Name": "OPTimeSetting",
                   "OPTimeSetting": value.strftime("%Y-%m-%d %H:%M:%S"), "SessionID": f"0x{session:08X}"})
            if response(connection).get("Ret") != 100:
                raise RuntimeError("Camera rejected the clock update.")
            number = 6
        packet(connection, session, number, 1452,
               {"Name": "OPTimeQuery", "SessionID": f"0x{session:08X}"})
        result = response(connection)
    if result.get("Ret") != 100 or not result.get("OPTimeQuery"):
        raise RuntimeError("Camera did not return its clock.")
    value = datetime.strptime(result["OPTimeQuery"], "%Y-%m-%d %H:%M:%S")
    return {"ok": True, "driver": "dvrip", "time": value.strftime("%Y-%m-%d %H:%M:%S")}


def dispatch(body):
    if not isinstance(body, dict) or not isinstance(body.get("camera"), dict):
        raise ValueError("Invalid Victure request.")
    camera = body["camera"]
    mode = body.get("mode")
    camera["ptz_type"] = mode
    operation = body.get("operation")
    if operation == "camera-time":
        return camera_time(camera, body.get("requested"))
    if operation != "ptz" or mode not in ("victure_dvrip", "victure_direct"):
        raise ValueError("Unsupported Victure operation.")
    action = body.get("action")
    speed = float(body.get("speed"))
    if not 0.05 <= speed <= 1.0:
        raise ValueError("Invalid PTZ speed.")
    if mode == "victure_direct":
        return direct_ptz(camera, action, speed)
    duration_ms = int(body.get("duration_ms", 300))
    if not 80 <= duration_ms <= 1500:
        raise ValueError("Invalid PTZ duration.")
    return dvrip_ptz(camera, action, speed, duration_ms)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # Camera endpoints and credentials must never enter access logs.

    def send_json(self, status, body):
        payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        expected = self.server.driver_token
        provided = self.headers.get("Authorization", "")
        if not hmac.compare_digest(provided, f"Bearer {expected}"):
            self.send_json(401, {"ok": False, "error": "Unauthorized"})
            return
        if self.path not in ("/v1/ptz", "/v1/camera-time"):
            self.send_json(404, {"ok": False, "error": "Not found"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 16384:
                raise ValueError("Invalid request size.")
            body = json.loads(self.rfile.read(size))
            body["operation"] = self.path.removeprefix("/v1/")
            result = dispatch(body)
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            self.send_json(400, {"ok": False, "error": "Invalid request"})
            return
        except Exception:
            self.send_json(502, {"ok": False, "error": "Camera control failed"})
            return
        self.send_json(200, result)


def main():
    token_file = os.environ["VICTURE_DRIVER_TOKEN_FILE"]
    with open(token_file, "r", encoding="utf-8") as handle:
        token = handle.read().strip()
    if not 32 <= len(token) <= 256:
        raise SystemExit("Driver token must be 32-256 characters.")
    host = os.environ.get("VICTURE_DRIVER_BIND", "127.0.0.1")
    port = int(os.environ.get("VICTURE_DRIVER_PORT", "8795"))
    server = ThreadingHTTPServer((host, port), Handler)
    server.driver_token = token
    server.serve_forever()


if __name__ == "__main__":
    main()
