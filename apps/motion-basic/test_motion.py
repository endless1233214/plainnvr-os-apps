import importlib.util
import os
import unittest
from pathlib import Path
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("motion", Path(__file__).with_name("motion.py"))
motion = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(motion)


class MotionDetection(unittest.TestCase):
    def test_start_stop_and_stream_end(self):
        still = bytes([0]) * 16
        changed = bytes([255]) * 16
        events = []
        with patch.object(motion, "SAMPLE_STEP", 1), patch.object(motion, "START_FRAMES", 2), \
                patch.object(motion, "STOP_FRAMES", 2):
            motion.detect([still, changed, still, still, still], lambda *event: events.append(event))
            self.assertEqual([event[0] for event in events], ["start", "stop"])
            events.clear()
            motion.detect([still, changed, still], lambda *event: events.append(event))
            self.assertEqual([event[0] for event in events], ["start", "stop"])

    def test_failed_delivery_retries_without_losing_start(self):
        still = bytes([0]) * 16
        changed = bytes([255]) * 16
        delivered = []
        attempts = []

        def emit(*event):
            attempts.append(event[0])
            if len(attempts) == 1:
                raise OSError("temporary receiver error")
            delivered.append(event[0])

        with patch.object(motion, "SAMPLE_STEP", 1), patch.object(motion, "START_FRAMES", 2):
            motion.detect([still, changed, still, changed], emit)
        self.assertEqual(attempts, ["start", "start", "stop"])
        self.assertEqual(delivered, ["start", "stop"])


if __name__ == "__main__":
    unittest.main()
