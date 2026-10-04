#!/usr/bin/env python3
"""Check that missing or changing LAN state never creates a wildcard listener."""

from pathlib import Path
import os
import subprocess
import unittest


INIT = Path(__file__).resolve().parents[1] / "package/network/utils/iperf3-server/files/iperf3-server.init"
STUBS = r'''
network_flush_cache() { :; }
network_get_ipaddr() {
    [ "$2" = lan ] && [ -n "$MOCK_ADDRESS" ] || return 1
    eval "$1=\$MOCK_ADDRESS"
}
network_get_device() {
    [ "$2" = lan ] && [ -n "$MOCK_DEVICE" ] || return 1
    eval "$1=\$MOCK_DEVICE"
}
procd_open_instance() { echo OPEN; }
procd_set_param() {
    [ "$1" = command ] || return 0
    shift
    printf '%s\n' "$@"
}
procd_close_instance() { echo CLOSE; }
procd_add_reload_trigger() { printf 'reload:%s\n' "$*"; }
procd_add_interface_trigger() { printf 'interface:%s\n' "$*"; }
'''


def invoke(action, address="192.168.50.1", device="br-lan"):
    script = INIT.read_text().replace(". /lib/functions/network.sh", ":")
    result = subprocess.run(
        ["sh"], input=STUBS + script + "\n" + action + "\n",
        env={**os.environ, "MOCK_ADDRESS": address, "MOCK_DEVICE": device},
        text=True, capture_output=True, check=True,
    )
    return result.stdout.splitlines()


class LanServerTest(unittest.TestCase):
    def test_address_and_device_both_restrict_ingress(self):
        for address, device in [("192.168.50.1", "br-lan"), ("10.20.30.4", "br-ap")]:
            with self.subTest(address=address, device=device):
                self.assertEqual(invoke("start_service", address, device), [
                    "OPEN", "/usr/bin/iperf3", "-s", "-4", "-B", address,
                    "--bind-dev", device, "-p", "5201", "CLOSE",
                ])

    def test_incomplete_lan_never_starts_an_unrestricted_server(self):
        for address, device in [("", "br-lan"), ("192.168.50.1", ""), ("", "")]:
            with self.subTest(address=address, device=device):
                self.assertEqual(invoke("start_service", address, device), [])

    def test_network_changes_rebind_the_listener(self):
        self.assertEqual(invoke("service_triggers"), [
            "reload:network",
            "interface:interface.* lan /etc/init.d/iperf3-server restart",
        ])


if __name__ == "__main__":
    unittest.main()
