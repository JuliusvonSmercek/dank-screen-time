"""Hardening against client-controlled strings and loose file permissions."""

import os
import stat
import tempfile
import tomllib
import unittest
from pathlib import Path

from screentime import categories, mcp, paths
from screentime.apps import Resolver


class UntrustedStringsTest(unittest.TestCase):
    # Any Wayland client chooses its own app_id; websites choose page titles.
    EVIL = 'x"\n[apps]\n"code_code" = "Hacked\x00\x1b[31m'

    def test_categories_toml_stays_valid(self):
        text, _ = categories.generate(Resolver(entries={}), None, [self.EVIL])
        parsed = tomllib.loads(text)  # must not raise
        self.assertNotIn("code_code", parsed.get("apps", {}))

    def test_quote_escapes_control_characters(self):
        q = categories._q('a"b\\c\nd\x00')
        self.assertEqual(tomllib.loads(f"k = {q}")["k"], 'a"b\\c\nd\x00')
        self.assertNotIn("\n", q)

    def test_unresolved_app_id_is_never_an_icon_path(self):
        info = Resolver(entries={}).resolve("/home/user/.ssh/id_rsa")
        self.assertEqual(info.icon, "")

    def test_mcp_clean(self):
        self.assertEqual(mcp.clean("a\x1b[31mb\n‮c"), "a [31mb c")
        self.assertEqual(len(mcp.clean("x" * 500)), 80)
        self.assertIsNone(mcp.clean(None))


class PermissionsTest(unittest.TestCase):
    def test_secure_dir_and_umask(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = paths.secure_dir(Path(tmp) / "data")
            self.assertEqual(stat.S_IMODE(d.stat().st_mode), 0o700)
            old = os.umask(0o022)
            try:
                paths.private_umask()
                f = d / "file"
                f.write_text("x")
                self.assertEqual(stat.S_IMODE(f.stat().st_mode), 0o600)
            finally:
                os.umask(old)


if __name__ == "__main__":
    unittest.main()
