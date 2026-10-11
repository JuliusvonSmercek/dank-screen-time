"""Window titles: redaction, normalization, retention, per-app breakdown."""

import datetime as dt
import unittest

from screentime import titles
from screentime.query import app_titles
from screentime.store import Store

STOPPED = {"running": False, "state": "stopped"}


class NormalizeTest(unittest.TestCase):
    def test_strips_app_suffix(self):
        self.assertEqual(titles.normalize("Pull requests · GitHub — Mozilla Firefox", "Firefox"),
                         "Pull requests · GitHub")
        self.assertEqual(titles.normalize("main.py - screen-time - Visual Studio Code", "Visual Studio Code"),
                         "main.py - screen-time")

    def test_strips_unread_counters_and_markers(self):
        self.assertEqual(titles.normalize("(3) Inbox - Mozilla Thunderbird", "Thunderbird Mail"), "Inbox")
        self.assertEqual(titles.normalize("● main.py - proj - Visual Studio Code", "Visual Studio Code"),
                         "main.py - proj")

    def test_title_that_is_only_the_app_name(self):
        self.assertEqual(titles.normalize("Spotify", "Spotify"), "")
        self.assertEqual(titles.normalize("Mozilla Firefox", "Firefox"), "")

    def test_keeps_titles_mentioning_the_app(self):
        self.assertEqual(titles.normalize("Firefox Add-ons — Mozilla Firefox", "Firefox"), "Firefox Add-ons")

    def test_redact_private_windows(self):
        self.assertEqual(titles.redact("Secret — Mozilla Firefox Private Browsing"), titles.PRIVATE_WINDOW)
        self.assertEqual(titles.redact("x" * 1000), "x" * titles.MAX_LEN)
        self.assertIsNone(titles.redact(""))


class TitleQueryTest(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)
        self.now = dt.datetime(2026, 10, 11, 12, 0).timestamp()

    def add(self, app, start, end, title):
        iid = self.store.open_interval(app, self.now + start, title)
        self.store.extend_interval(iid, self.now + end)

    def test_groups_and_ranks(self):
        self.add("firefox", -3000, -2000, "GitHub — Mozilla Firefox")
        self.add("firefox", -2000, -1900, "(2) GitHub — Mozilla Firefox")
        self.add("firefox", -1900, -1400, "YouTube — Mozilla Firefox")
        self.add("firefox", -5000, -4000, None)          # before title tracking was on
        self.add("code", -1400, -100, "main.py - Visual Studio Code")
        t = app_titles(self.store, "firefox", now=self.now, app_name="Firefox", status=STOPPED)
        self.assertEqual([(i["title"], i["seconds"]) for i in t["items"]], [("GitHub", 1100), ("YouTube", 500)])
        self.assertEqual(t["unrecorded_seconds"], 1000)
        self.assertEqual(t["recorded_seconds"], 1600)

    def test_limit_folds_into_other(self):
        for i in range(5):
            self.add("firefox", -1000 + i * 100, -1000 + i * 100 + 50 + i, f"Page {i} — Mozilla Firefox")
        t = app_titles(self.store, "firefox", now=self.now, app_name="Firefox", status=STOPPED, limit=2)
        self.assertEqual(len(t["items"]), 2)
        self.assertEqual(t["other_seconds"], 50 + 51 + 52)

    def test_purge_keeps_time(self):
        self.add("firefox", -40 * 86400, -40 * 86400 + 60, "Old page")
        self.add("firefox", -100, -40, "New page")
        self.assertEqual(self.store.purge_titles(self.now - 30 * 86400), 1)
        rows = [(r[4], round(r[3] - r[2])) for r in self.store.recent(10)]
        self.assertIn((None, 60), rows)
        self.assertIn(("New page", 60), rows)


if __name__ == "__main__":
    unittest.main()
