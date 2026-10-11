"""niri event model, logind monitor parsing, app resolution, categories, config."""

import tempfile
import unittest
from pathlib import Path

from screentime import categories, config
from screentime.apps import Resolver, prettify, scan_desktop_entries
from screentime.niri import WindowModel
from screentime.session import _locked_from, parse_monitor_line


def win(wid, app_id, focused=False):
    return {"id": wid, "title": "t", "app_id": app_id, "pid": 1, "workspace_id": 1, "is_focused": focused}


class WindowModelTest(unittest.TestCase):
    # Event shapes as captured from niri 26.04.
    def test_snapshot_then_focus_changes(self):
        m = WindowModel()
        m.handle({"WindowsChanged": {"windows": [win(5, "code_code"), win(22, "thunderbird_thunderbird", True)]}})
        self.assertEqual(m.focused()["app_id"], "thunderbird_thunderbird")
        self.assertTrue(m.handle({"WindowFocusChanged": {"id": 5}}))
        self.assertEqual(m.focused()["app_id"], "code_code")
        self.assertTrue(m.handle({"WindowFocusChanged": {"id": None}}))
        self.assertIsNone(m.focused())

    def test_open_and_close(self):
        m = WindowModel()
        m.handle({"WindowsChanged": {"windows": [win(1, "a", True)]}})
        m.handle({"WindowOpenedOrChanged": {"window": win(2, "b", True)}})
        self.assertEqual(m.focused()["app_id"], "b")
        self.assertTrue(m.handle({"WindowClosed": {"id": 2}}))
        self.assertIsNone(m.focused())
        self.assertFalse(m.handle({"WindowClosed": {"id": 1}}) and m.focused())

    def test_irrelevant_events(self):
        m = WindowModel()
        self.assertFalse(m.handle({"WindowFocusTimestampChanged": {"id": 1, "focus_timestamp": {}}}))
        self.assertFalse(m.handle({"OverviewOpenedOrClosed": {"is_open": True}}))
        self.assertFalse(m.handle({"KeyboardLayoutSwitched": {"idx": 0}}))


class LogindParseTest(unittest.TestCase):
    S = "/org/freedesktop/login1/session/_33"

    def test_prepare_for_sleep(self):
        line = "/org/freedesktop/login1: org.freedesktop.login1.Manager.PrepareForSleep (true,)"
        self.assertEqual(parse_monitor_line(line, self.S), {"sleeping": True})
        line = "/org/freedesktop/login1: org.freedesktop.login1.Manager.PrepareForSleep (false,)"
        self.assertEqual(parse_monitor_line(line, self.S), {"sleeping": False})

    def test_locked_hint(self):
        line = (f"{self.S}: org.freedesktop.DBus.Properties.PropertiesChanged "
                "('org.freedesktop.login1.Session', {'LockedHint': <true>}, @as [])")
        self.assertEqual(parse_monitor_line(line, self.S), {"LockedHint": True})

    def test_other_session_ignored(self):
        line = ("/org/freedesktop/login1/session/_34: org.freedesktop.DBus.Properties.PropertiesChanged "
                "('org.freedesktop.login1.Session', {'LockedHint': <true>}, @as [])")
        self.assertEqual(parse_monitor_line(line, self.S), {})

    def test_inactive_session_counts_as_locked(self):
        self.assertTrue(_locked_from({"LockedHint": False, "Active": False}, False))
        self.assertFalse(_locked_from({"LockedHint": False, "Active": True}, True))


def write_desktop(dirpath: Path, name: str, body: str):
    (dirpath / "applications").mkdir(parents=True, exist_ok=True)
    (dirpath / "applications" / name).write_text("[Desktop Entry]\nType=Application\n" + body)


class ResolverTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.user, self.snap = base / "user", base / "snap"
        write_desktop(self.snap, "code_code.desktop",
                      "Name=Visual Studio Code\nIcon=/snap/code/icon.png\nStartupWMClass=code_code\n"
                      "Exec=/snap/bin/code %F\nCategories=Development;IDE;\n"
                      "[Desktop Action new]\nName=New Window\n")
        write_desktop(self.snap, "spotify_spotify.desktop",
                      "Name=Spotify\nIcon=spotify\nStartupWMClass=spotify\nCategories=Audio;Music;\n")
        write_desktop(self.snap, "firefox_firefox.desktop", "Name=Firefox\nIcon=firefox\nCategories=WebBrowser;\n")
        write_desktop(self.user, "whatsapp.desktop",
                      "Name=WhatsApp\nIcon=/home/u/whatsapp.png\nStartupWMClass=whatsapp\n"
                      "Exec=/opt/whatsapp-app/WhatsApp %U\nCategories=Network;InstantMessaging;\n")
        write_desktop(self.user, "org.gnome.Nautilus.desktop", "Name=Files\nName[de]=Dateien\nIcon=nautilus\n")
        write_desktop(self.user, "myapp.desktop", "Name=My App\nExec=/opt/myapp/bin/run-me\n")
        write_desktop(self.user, "hidden-helper.desktop", "Name=Helper\nNoDisplay=true\nStartupWMClass=dup\n")
        write_desktop(self.user, "visible.desktop", "Name=Visible\nStartupWMClass=dup\n")
        # User dir shadows system dir for the same desktop id.
        write_desktop(self.snap, "myapp.desktop", "Name=Shadowed\n")
        self.entries = scan_desktop_entries([self.user, self.snap])

    def tearDown(self):
        self.tmp.cleanup()

    def r(self, app_id, exes=None):
        return Resolver(self.entries, exes).resolve(app_id)

    def test_exact_and_wmclass(self):
        info = self.r("code_code")
        self.assertEqual((info.name, info.icon), ("Visual Studio Code", "/snap/code/icon.png"))

    def test_case_insensitive_wmclass(self):
        self.assertEqual(self.r("Spotify").desktop_id, "spotify_spotify")

    def test_snap_suffix(self):
        self.assertEqual(self.r("firefox").desktop_id, "firefox_firefox")

    def test_prefix_match(self):
        self.assertEqual(self.r("whatsapp-nativefier-d40211").name, "WhatsApp")

    def test_exe_fallback(self):
        self.assertEqual(self.r("weird-id", {"weird-id": "/opt/myapp/bin/run-me"}).name, "My App")

    def test_shadowing_and_visible_preferred(self):
        self.assertEqual(self.r("myapp").name, "My App")
        self.assertEqual(self.r("dup").desktop_id, "visible")

    def test_unresolved_gets_pretty_name_not_unknown(self):
        info = self.r("com.example.cool-tool")
        self.assertIsNone(info.desktop_id)
        self.assertEqual(info.name, "Cool Tool")
        self.assertEqual(prettify("foo_foo"), "Foo")

    def test_generate_categories(self):
        text, added = categories.generate(Resolver(self.entries), None, ["whatsapp-nativefier-d40211"])
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as fh:
            fh.write(text)
        mapping = categories.load(Path(fh.name))
        self.assertEqual(mapping["code_code"], "Development")
        self.assertEqual(mapping["firefox_firefox"], "Browsing")
        self.assertEqual(mapping["whatsapp"], "Communication")
        self.assertEqual(mapping["spotify_spotify"], "Media")
        self.assertNotIn("whatsapp-nativefier-d40211", mapping)  # covered by desktop id
        # Regenerating keeps user edits and adds nothing new.
        edited = text.replace('"code_code" = "Development"', '"code_code" = "Work"')
        text2, added2 = categories.generate(Resolver(self.entries), edited)
        self.assertEqual(added2, 0)
        self.assertIn('"code_code" = "Work"', text2)

    def test_categorizer_uses_desktop_id(self):
        c = categories.Categorizer({"whatsapp": "Communication"})
        self.assertEqual(c.category("whatsapp-nativefier-d40211", "whatsapp"), "Communication")
        self.assertIsNone(c.category("other", None))


class ConfigTest(unittest.TestCase):
    def test_set_preserves_comments(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text("# idle\nidle_timeout = 300\n# titles\ntrack_titles = false\n")
            config.set_value("idle_timeout", 120, path)
            config.set_value("track_titles", True, path)
            config.set_value("day_start_hour", 4, path)
            text = path.read_text()
            self.assertIn("# idle\nidle_timeout = 120\n", text)
            cfg = config.load(path)
            self.assertEqual((cfg.idle_timeout, cfg.track_titles, cfg.day_start_hour), (120, True, 4))

    def test_invalid_file_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text("idle_timeout = = nope")
            self.assertEqual(config.load(path), config.Config())

    def test_parse_value(self):
        self.assertIs(config.parse_value("track_titles", "on"), True)
        self.assertEqual(config.parse_value("idle_timeout", "60"), 60)
        with self.assertRaises(ValueError):
            config.parse_value("track_titles", "maybe")


if __name__ == "__main__":
    unittest.main()
