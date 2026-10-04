import json
import os
import stat
import tempfile
import unittest

import driver


class DriverTests(unittest.TestCase):
    def test_local_ip_validation(self):
        self.assertEqual(driver._local_ip("192.168.1.199"), "192.168.1.199")
        with self.assertRaises(driver.DriverError):
            driver._local_ip("8.8.8.8")

    def test_invoke_uses_stdin_and_redacts_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            helper = os.path.join(directory, "helper")
            with open(helper, "w", encoding="utf-8") as stream:
                stream.write(
                    "#!/usr/bin/env python3\n"
                    "import json,sys\n"
                    "request=json.load(sys.stdin)\n"
                    "print(json.dumps({'ok': True, 'echo': {'operation': request['operation'], 'host': request['host']}}))\n"
                )
            os.chmod(helper, stat.S_IRWXU)
            old = os.environ.get("TAPOCTL_BIN")
            os.environ["TAPOCTL_BIN"] = helper
            try:
                response = driver.invoke(
                    {"host": "192.168.1.199", "username": "user", "password": "secret"},
                    "state",
                )
            finally:
                if old is None:
                    os.environ.pop("TAPOCTL_BIN", None)
                else:
                    os.environ["TAPOCTL_BIN"] = old
            self.assertTrue(response["ok"])
            self.assertEqual(response["echo"]["operation"], "state")

    def test_control_allowlist(self):
        with self.assertRaises(driver.DriverError):
            driver.invoke(
                {"host": "192.168.1.199", "username": "user", "password": "secret"},
                "set",
                "shell",
                True,
            )


if __name__ == "__main__":
    unittest.main()
