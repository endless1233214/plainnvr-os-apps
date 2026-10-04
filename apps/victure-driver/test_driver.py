import http.client
import json
import threading
import unittest
from unittest import mock

import driver


class FakeCameraConnection:
    def __init__(self):
        self.sent = []
        self.replies = [self._reply({"Ret": 100, "SessionID": "0x00000001"})]

    def _reply(self, body):
        payload = json.dumps(body).encode()
        return driver.HEADER.pack(255, 1, 0, 1, 1, 0, 0, 1000, len(payload)) + payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def settimeout(self, _):
        pass

    def sendall(self, data):
        self.sent.append(data)

    def recv(self, size):
        if not self.replies:
            raise AssertionError("Unexpected camera read")
        head = self.replies[0]
        part, self.replies[0] = head[:size], head[size:]
        if not self.replies[0]:
            self.replies.pop(0)
        return part


class DriverTests(unittest.TestCase):
    def test_direct_step_posts_only_expected_action_and_step(self):
        class Reply:
            status = 200

            def read(self, _limit):
                return b"ok"

        class Connection:
            def __init__(self, host, port, timeout):
                self.host, self.port, self.timeout = host, port, timeout

            def request(self, method, path, body, headers):
                self.request_data = method, path, body, headers

            def getresponse(self):
                return Reply()

            def close(self):
                pass

        connections = []

        def connect(*args, **kwargs):
            value = Connection(*args, **kwargs)
            connections.append(value)
            return value

        with mock.patch.object(driver.http.client, "HTTPConnection", side_effect=connect):
            result = driver.direct_ptz({"ptz_url": "http://192.168.1.3:8088"}, "right", 0.5)
        self.assertTrue(result["ok"])
        self.assertEqual((connections[0].host, connections[0].port), ("192.168.1.3", 8088))
        self.assertEqual(connections[0].request_data[0:3],
                         ("POST", "/ptz", "action=right&step=32"))

    def test_dvrip_clock_query_uses_authenticated_session(self):
        socket = FakeCameraConnection()
        socket.replies.append(socket._reply({"Ret": 100, "OPTimeQuery": "2026-10-04 12:34:56"}))
        with mock.patch.object(driver.socket, "create_connection", return_value=socket):
            result = driver.camera_time({"ptz_type": "victure_dvrip",
                "time_sync_supported": True, "ptz_url": "dvrip://192.168.1.2",
                "ptz_profile_token": "camera-hash"}, None)
        self.assertEqual(result["time"], "2026-10-04 12:34:56")
        self.assertEqual(len(socket.sent), 2)  # login and query

    def test_target_rejects_public_and_dns_hosts(self):
        for value in ("http://8.8.8.8:8088", "http://camera.example:8088", "http://127.0.0.1:8088"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                driver.target({"ptz_url": value}, "victure_direct")
        self.assertEqual(driver.target({"ptz_url": "http://192.168.1.2"}, "victure_direct")[:2],
                         ("192.168.1.2", 8088))

    def test_dvrip_requires_camera_specific_credential(self):
        with self.assertRaises(ValueError):
            driver.target({"ptz_url": "dvrip://192.168.1.2"}, "victure_dvrip")

    def test_both_control_modes_dispatch(self):
        socket = FakeCameraConnection()
        with mock.patch.object(driver.socket, "create_connection", return_value=socket), \
             mock.patch.object(driver.time, "sleep"):
            result = driver.dispatch({"operation": "ptz", "mode": "victure_dvrip",
                "camera": {"ptz_url": "dvrip://192.168.1.2", "ptz_profile_token": "camera-hash"},
                "action": "left", "speed": 0.5, "duration_ms": 200})
        self.assertTrue(result["ok"])
        self.assertEqual(len(socket.sent), 3)  # login, move, stop

        with mock.patch.object(driver, "direct_ptz", return_value={"ok": True}) as direct:
            result = driver.dispatch({"operation": "ptz", "mode": "victure_direct",
                "camera": {"ptz_url": "http://192.168.1.3:8088"},
                "action": "right", "speed": 0.5})
        self.assertTrue(result["ok"])
        direct.assert_called_once()

    def test_http_requires_token_and_never_returns_camera_secret(self):
        server = driver.ThreadingHTTPServer(("127.0.0.1", 0), driver.Handler)
        server.driver_token = "a" * 40
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            body = json.dumps({"camera": {"ptz_url": "http://192.168.1.2:8088"},
                               "mode": "victure_direct", "action": "home", "speed": 0.5})
            connection.request("POST", "/v1/ptz", body, {"Content-Type": "application/json"})
            response = connection.getresponse()
            self.assertEqual(response.status, 401)
            response.read()
            connection.request("POST", "/v1/ptz", body,
                               {"Authorization": "Bearer " + "a" * 40})
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertTrue(json.loads(response.read())["ok"])
            connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
