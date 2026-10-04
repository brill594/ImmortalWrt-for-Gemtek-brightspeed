#!/usr/bin/env python3
"""Preserved settings must not select a theme with only branding left behind."""

from pathlib import Path
import os
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "target/linux/airoha/an7581/base-files/etc/uci-defaults/99-xr1710g-theme-fallback"
STUBS = '''
board_name() { printf '%s\\n' "$BOARD"; }
uci() {
    shift
    case "$1" in
        get) printf '%s\\n' "$THEME" ;;
        *) printf '%s\\n' "$*" ;;
    esac
}
'''


class ThemeFallbackTest(unittest.TestCase):
    def run_case(self, board, theme, argon_css, bootstrap_css):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "argon/background").mkdir(parents=True)
            for path, present in [("argon/css/cascade.css", argon_css),
                                  ("bootstrap/cascade.css", bootstrap_css)]:
                if present:
                    target = root / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.touch()
            script = SCRIPT.read_text().replace(". /lib/functions/system.sh", ":")
            script = script.replace("/www/luci-static/", directory + "/")
            return subprocess.run(
                ["sh"], input=STUBS + script, text=True, capture_output=True,
                env={**os.environ, "BOARD": board, "THEME": theme}, check=True,
            ).stdout.splitlines()

    def test_branding_directory_does_not_prevent_recovery(self):
        self.assertEqual(self.run_case("gemtek,xr1710g-ubi", "/luci-static/argon", False, True), [
            "set luci.main.mediaurlbase=/luci-static/bootstrap", "commit luci",
        ])

    def test_valid_choices_and_other_boards_are_preserved(self):
        for board, theme, argon, bootstrap in [
            ("gemtek,xr1710g-ubi", "/luci-static/argon", True, True),
            ("gemtek,xr1710g-ubi", "/luci-static/bootstrap", False, True),
            ("gemtek,xg2010g-ubi", "/luci-static/argon", False, True),
            ("gemtek,xr1710g-ubi", "/luci-static/argon", False, False),
        ]:
            with self.subTest(board=board, theme=theme, argon=argon, bootstrap=bootstrap):
                self.assertEqual(self.run_case(board, theme, argon, bootstrap), [])


if __name__ == "__main__":
    unittest.main()
