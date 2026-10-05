#!/usr/bin/env python3
"""MCU replies must avoid the data backlog without moving other NAPI workers."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "package/network/config/airoha-an7581-mt7996-board/files/usr/libexec/platform/packet-steering.sh"
STUBS = r'''
board_name() { printf '%s\n' "$MOCK_BOARD"; }
uci() { :; }
taskset() { printf '%s:%s\n' "$2" "$3" >> "$TRACE_FILE"; }
'''

class McuSteeringTest(unittest.TestCase):
    def invoke(self, mode="", board="gemtek,xr1710g-ubi", mcu_pid="1002"):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for cpu in range(4):
                path = root / "cpu" / ("cpu%d" % cpu)
                path.mkdir(parents=True)
                (path / "online").write_text("1\n")
            for pid, name in [(1000, "napi/phy0-0"), (1001, "napi/phy0-0"),
                              (1002, "napi/phy0-0"), (1003, "napi/phy0-0"),
                              (1004, "napi/phy0-0"), (1005, "mt76-tx phy0")]:
                path = root / "proc" / str(pid) / "task" / str(pid)
                path.mkdir(parents=True)
                (path / "comm").write_text(name + "\n")
            pid_file = root / "debug/phy0/mt76/mcu_wa_napi_pid"
            if mcu_pid is not None:
                pid_file.parent.mkdir(parents=True)
                pid_file.write_text(mcu_pid + "\n")
            generic = root / "generic"
            generic.write_text('#!/bin/sh\nprintf "generic:%s\\n" "$*" >> "$TRACE_FILE"\n')
            generic.chmod(0o755)
            trace = root / "trace"
            text = SCRIPT.read_text().replace(". /lib/functions.sh", ":").replace(". /lib/functions/system.sh", ":")
            text = text.replace("/sys/devices/system/cpu", str(root / "cpu"))
            text = text.replace("/sys/kernel/debug/ieee80211", str(root / "debug"))
            text = text.replace("/proc/", str(root / "proc") + "/")
            text = text.replace("/usr/libexec/network/packet-steering.uc", str(generic))
            subprocess.run(["sh", "-s", "--", mode], input=STUBS + text,
                           env={**os.environ, "MOCK_BOARD": board, "TRACE_FILE": str(trace)},
                           text=True, check=True, capture_output=True)
            return trace.read_text().splitlines()

    def test_mcu_isolated_without_shifting_data_workers(self):
        fixed = self.invoke()
        baseline = self.invoke(mcu_pid="0")
        self.assertIn("1:1002", fixed)
        self.assertIn("3:1002", baseline)
        self.assertEqual([line for line in fixed if not line.endswith(":1002")],
                         [line for line in baseline if not line.endswith(":1002")])
        self.assertEqual(fixed, ["generic:", "1:1000", "2:1001", "1:1002",
                                 "1:1003", "2:1004", "2:1005"])

    def test_user_disable_and_other_boards_keep_generic_policy(self):
        self.assertEqual(self.invoke(mode="0"), ["generic:0"])
        self.assertEqual(self.invoke(board="gemtek,w1700k-ubi"), ["generic:"])

    def test_missing_or_invalid_queue_identity_preserves_rotation(self):
        for value in [None, "0", "bad", "1002 invalid"]:
            self.assertIn("3:1002", self.invoke(mcu_pid=value))

    def test_mode_two_keeps_control_queue_policy(self):
        self.assertIn("1:1002", self.invoke(mode="2"))

if __name__ == "__main__":
    unittest.main()
