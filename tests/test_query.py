"""Aggregation: midnight rollover, DST, day_start_hour, averages, live interval."""

import datetime as dt
import os
import time
import unittest

from screentime.apps import Resolver
from screentime.categories import Categorizer
from screentime.query import format_duration, summarize
from screentime.store import Store

STOPPED = {"running": False, "state": "stopped", "current_app": None}


def ts(*args) -> float:
    return dt.datetime(*args).timestamp()  # local time


class TZMixin:
    tz = "Europe/Berlin"

    def setUp(self):
        self._old_tz = os.environ.get("TZ")
        os.environ["TZ"] = self.tz
        time.tzset()
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)
        self.resolver = Resolver(entries={})

    def tearDown(self):
        if self._old_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = self._old_tz
        time.tzset()

    def add(self, app, start, end):
        iid = self.store.open_interval(app, start)
        self.store.extend_interval(iid, end)
        return iid

    def summary(self, kind, now, **kw):
        kw.setdefault("status", STOPPED)
        return summarize(self.store, kind=kind, now=now, resolver=self.resolver, **kw)


class QueryTest(TZMixin, unittest.TestCase):
    def test_midnight_rollover_split(self):
        self.add("code", ts(2026, 10, 10, 23, 30), ts(2026, 10, 11, 0, 45))
        now = ts(2026, 10, 11, 12, 0)
        today = self.summary("day", now)
        self.assertEqual(today["total_seconds"], 45 * 60)
        self.assertEqual(today["chart"]["buckets"][0]["seconds"], 45 * 60)
        yesterday = self.summary("day", now, anchor=dt.date(2026, 10, 10))
        self.assertEqual(yesterday["total_seconds"], 30 * 60)
        self.assertEqual(yesterday["chart"]["buckets"][23]["seconds"], 30 * 60)

    def test_day_start_hour(self):
        # With days starting at 04:00, 01:00-02:00 belongs to the previous day.
        self.add("code", ts(2026, 10, 11, 1, 0), ts(2026, 10, 11, 2, 0))
        now = ts(2026, 10, 11, 12, 0)
        s = self.summary("day", now, day_start_hour=4)
        self.assertEqual(s["range"]["anchor"], "2026-10-11")
        self.assertEqual(s["total_seconds"], 0)
        prev = self.summary("day", now, day_start_hour=4, anchor=dt.date(2026, 10, 10))
        self.assertEqual(prev["total_seconds"], 3600)
        self.assertEqual(prev["chart"]["buckets"][0]["hour"], 4)

    def test_dst_fall_back_day_has_25_hours(self):
        # 2026-10-25: Europe/Berlin goes from CEST to CET at 03:00.
        self.add("code", ts(2026, 10, 25, 0, 0), ts(2026, 10, 26, 0, 0))
        s = self.summary("day", ts(2026, 10, 27, 12, 0), anchor=dt.date(2026, 10, 25))
        self.assertEqual(s["total_seconds"], 25 * 3600)
        self.assertEqual(sum(b["seconds"] for b in s["chart"]["buckets"]), 25 * 3600)

    def test_dst_spring_forward_day_has_23_hours(self):
        self.add("code", ts(2026, 3, 29, 0, 0), ts(2026, 3, 30, 0, 0))
        s = self.summary("day", ts(2026, 3, 31, 12, 0), anchor=dt.date(2026, 3, 29))
        self.assertEqual(s["total_seconds"], 23 * 3600)

    def test_week_is_monday_to_sunday(self):
        now = ts(2026, 10, 11, 12, 0)  # a Sunday
        self.add("code", ts(2026, 10, 5, 9, 0), ts(2026, 10, 5, 10, 0))  # Monday
        self.add("code", ts(2026, 10, 4, 9, 0), ts(2026, 10, 4, 10, 0))  # previous Sunday
        s = self.summary("week", now)
        self.assertEqual(s["range"]["start"], "2026-10-05")
        self.assertEqual(s["range"]["end"], "2026-10-11")
        self.assertEqual(s["total_seconds"], 3600)
        self.assertEqual([b["seconds"] for b in s["chart"]["buckets"]], [3600, 0, 0, 0, 0, 0, 0])
        self.assertTrue(s["chart"]["buckets"][6]["is_current"])

    def test_seven_day_average_counts_empty_days(self):
        now = ts(2026, 10, 11, 12, 0)
        # 7 hours on one day of the previous seven -> average 1 h/day.
        self.add("code", ts(2026, 10, 8, 8, 0), ts(2026, 10, 8, 15, 0))
        self.add("code", ts(2026, 10, 11, 8, 0), ts(2026, 10, 11, 10, 0))
        s = self.summary("day", now)
        self.assertEqual(s["average_seconds"], 3600)
        self.assertEqual(s["vs_average_pct"], 100)

    def test_today_excluded_from_its_own_average(self):
        now = ts(2026, 10, 11, 12, 0)
        self.add("code", ts(2026, 10, 11, 8, 0), ts(2026, 10, 11, 10, 0))
        s = self.summary("day", now)
        self.assertEqual(s["average_seconds"], 0)
        self.assertIsNone(s["vs_average_pct"])

    def test_app_history_last_seven_days(self):
        now = ts(2026, 10, 11, 12, 0)
        self.add("code", ts(2026, 10, 5, 9, 0), ts(2026, 10, 5, 9, 30))
        self.add("code", ts(2026, 10, 11, 9, 0), ts(2026, 10, 11, 9, 10))
        s = self.summary("day", now)
        self.assertEqual(s["history_dates"][0], "2026-10-05")
        self.assertEqual(s["apps"][0]["history"], [1800, 0, 0, 0, 0, 0, 600])

    def test_live_interval_extended_to_now(self):
        now = ts(2026, 10, 11, 12, 0)
        iid = self.add("code", now - 100, now - 3)  # last heartbeat 3 s ago
        status = {"running": True, "state": "active", "current_interval_id": iid}
        s = self.summary("day", now, status=status)
        self.assertEqual(s["total_seconds"], 100)

    def test_future_part_of_interval_ignored(self):
        now = ts(2026, 10, 11, 12, 0)
        self.add("code", now - 60, now + 600)
        self.assertEqual(self.summary("day", now)["total_seconds"], 60)

    def test_categories_and_unmapped_apps(self):
        now = ts(2026, 10, 11, 12, 0)
        self.add("code", now - 3000, now - 2000)
        self.add("firefox", now - 2000, now - 1500)
        self.add("mystery", now - 1500, now - 1400)
        cats = Categorizer({"code": "Development", "firefox": "Browsing"})
        s = self.summary("day", now, categorizer=cats)
        got = [(c["name"], c["seconds"], c["is_app"]) for c in s["categories"]]
        self.assertEqual(got, [("Development", 1000, False), ("Browsing", 500, False), ("Mystery", 100, True)])
        self.assertAlmostEqual(sum(a["share"] for a in s["apps"]), 1.0)

    def test_navigation(self):
        now = ts(2026, 10, 11, 12, 0)
        self.add("code", ts(2026, 10, 1, 9, 0), ts(2026, 10, 1, 10, 0))
        s = self.summary("day", now)
        self.assertEqual(s["range"]["prev"], "2026-10-10")
        self.assertIsNone(s["range"]["next"])
        old = self.summary("day", now, anchor=dt.date(2026, 10, 1))
        self.assertIsNone(old["range"]["prev"])  # no data before Oct 1
        self.assertEqual(old["range"]["next"], "2026-10-02")
        future = self.summary("day", now, anchor=dt.date(2026, 12, 1))
        self.assertEqual(future["range"]["anchor"], "2026-10-11")

    def test_empty_database(self):
        s = summarize(None, kind="week", now=ts(2026, 10, 11, 12), resolver=self.resolver, status=STOPPED)
        self.assertEqual(s["total_seconds"], 0)
        self.assertEqual(s["apps"], [])


class FormatTest(unittest.TestCase):
    def test_format_duration(self):
        self.assertEqual(format_duration(0), "0 min")
        self.assertEqual(format_duration(20), "< 1 min")
        self.assertEqual(format_duration(45 * 60), "45 min")
        self.assertEqual(format_duration(2 * 3600), "2 h")
        self.assertEqual(format_duration(2 * 3600 + 15 * 60), "2 h 15 min")


if __name__ == "__main__":
    unittest.main()
