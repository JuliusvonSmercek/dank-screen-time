"""Interval logic: focus switches, idle, lock, suspend gaps, crash recovery."""

import os
import tempfile
import unittest

from screentime.store import Store
from screentime.tracker import Tracker

T0 = 1_760_000_000.0  # arbitrary wall-clock origin


class Clock:
    """Fake wall/monotonic/boottime clocks."""

    def __init__(self):
        self.wall, self.mono, self.boot = T0, 1000.0, 1000.0

    def advance(self, seconds):
        self.wall += seconds
        self.mono += seconds
        self.boot += seconds

    def suspend(self, seconds):
        # Only wall and boottime run while suspended.
        self.wall += seconds
        self.boot += seconds

    def beat(self, tracker):
        tracker.heartbeat(self.wall, self.mono, self.boot)


def rows(store):
    return [(a, s - T0, e - T0) for _, a, s, e in store.intervals_between(0, 1e12)]


class TrackerTest(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)
        self.t = Tracker(self.store)
        self.c = Clock()

    def test_focus_switches(self):
        self.t.set_focus("firefox", "a", self.c.wall)
        self.c.advance(10)
        self.t.set_focus("code", "b", self.c.wall)
        self.c.advance(5)
        self.t.set_focus("firefox", "c", self.c.wall)
        self.c.advance(2)
        self.t.stop(self.c.wall)
        self.assertEqual(rows(self.store), [("firefox", 0, 10), ("code", 10, 15), ("firefox", 15, 17)])

    def test_same_app_other_window_keeps_interval(self):
        self.t.set_focus("code", "file1", self.c.wall)
        self.c.advance(10)
        self.t.set_focus("code", "file2", self.c.wall)
        self.c.advance(10)
        self.t.stop(self.c.wall)
        self.assertEqual(rows(self.store), [("code", 0, 20)])

    def test_titles_split_when_enabled(self):
        self.t.set_track_titles(True, self.c.wall)
        self.t.set_focus("code", "file1", self.c.wall)
        self.c.advance(10)
        self.t.set_focus("code", "file2", self.c.wall)
        self.c.advance(10)
        self.t.stop(self.c.wall)
        got = [(a, s - T0, e - T0, title) for _, a, s, e, title in reversed(self.store.recent(10))]
        self.assertEqual(got, [("code", 0, 10, "file1"), ("code", 10, 20, "file2")])

    def test_titles_not_stored_by_default(self):
        self.t.set_focus("code", "secret.txt", self.c.wall)
        self.c.advance(5)
        self.t.stop(self.c.wall)
        self.assertIsNone(self.store.recent(1)[0][4])

    def test_no_focus_is_not_counted(self):
        self.t.set_focus("firefox", None, self.c.wall)
        self.c.advance(10)
        self.t.set_focus(None, None, self.c.wall)  # layer-shell / empty workspace
        self.c.advance(30)
        self.t.set_focus("firefox", None, self.c.wall)
        self.c.advance(5)
        self.t.stop(self.c.wall)
        self.assertEqual(rows(self.store), [("firefox", 0, 10), ("firefox", 40, 45)])
        self.assertEqual(self.t.state, "active")

    def test_idle_stops_and_resumes(self):
        self.t.set_focus("code", None, self.c.wall)
        self.c.advance(60)
        self.t.set_idle(True, self.c.wall)
        self.assertEqual(self.t.state, "idle")
        self.c.advance(600)
        self.c.beat(self.t)
        self.t.set_idle(False, self.c.wall)
        self.c.advance(10)
        self.t.stop(self.c.wall)
        self.assertEqual(rows(self.store), [("code", 0, 60), ("code", 660, 670)])

    def test_focus_change_while_idle_counts_nothing(self):
        self.t.set_idle(True, self.c.wall)
        self.t.set_focus("code", None, self.c.wall)
        self.c.advance(30)
        self.t.set_focus("firefox", None, self.c.wall)
        self.c.advance(30)
        self.t.set_idle(False, self.c.wall)
        self.c.advance(5)
        self.t.stop(self.c.wall)
        self.assertEqual(rows(self.store), [("firefox", 60, 65)])

    def test_lock_stops_counting(self):
        self.t.set_focus("code", None, self.c.wall)
        self.c.advance(20)
        self.t.set_locked(True, self.c.wall)
        self.c.advance(300)
        self.c.beat(self.t)
        self.t.set_locked(False, self.c.wall)
        self.c.advance(20)
        self.t.stop(self.c.wall)
        self.assertEqual(rows(self.store), [("code", 0, 20), ("code", 320, 340)])

    def test_prepare_for_sleep(self):
        self.t.set_focus("code", None, self.c.wall)
        self.c.beat(self.t)
        self.c.advance(20)
        self.t.set_sleeping(True, self.c.wall)
        self.c.suspend(3600)
        self.t.set_sleeping(False, self.c.wall)
        self.c.advance(2)
        self.c.beat(self.t)  # sees the boottime gap, must not break the new interval
        self.c.advance(8)
        self.t.stop(self.c.wall)
        self.assertEqual(rows(self.store), [("code", 0, 20), ("code", 3620, 3630)])

    def test_suspend_detected_from_clock_gap_without_logind(self):
        self.t.set_focus("code", None, self.c.wall)
        self.c.beat(self.t)
        for _ in range(4):
            self.c.advance(5)
            self.c.beat(self.t)
        self.c.advance(2)  # awake a little after the last beat, then suspend
        self.c.suspend(7200)
        self.c.advance(1)
        self.c.beat(self.t)
        self.c.advance(10)
        self.t.stop(self.c.wall)
        # Ends at the last beat before the gap (loses < 1 heartbeat), restarts after.
        self.assertEqual(rows(self.store), [("code", 0, 20), ("code", 7223, 7233)])

    def test_lost_resume_signal_does_not_stop_tracking_forever(self):
        self.t.set_focus("code", None, self.c.wall)
        self.c.beat(self.t)
        self.t.set_sleeping(True, self.c.wall)
        self.c.suspend(600)
        self.c.advance(1)
        self.c.beat(self.t)  # PrepareForSleep(false) never arrived
        self.assertFalse(self.t.sleeping)
        self.c.advance(10)
        self.t.stop(self.c.wall)
        self.assertEqual(rows(self.store), [("code", 601, 611)])

    def test_wall_clock_jump_backwards(self):
        self.t.set_focus("code", None, self.c.wall)
        self.c.beat(self.t)
        self.c.advance(5)
        self.c.beat(self.t)
        self.c.mono += 5
        self.c.boot += 5
        self.c.wall -= 3600  # clock set back an hour
        self.c.beat(self.t)
        self.c.advance(10)
        self.t.stop(self.c.wall)
        # Rows "from the future" of the new clock are dropped; tracking resumes.
        self.assertEqual(rows(self.store), [("code", -3595, -3585)])

    def test_heartbeat_extends_open_interval(self):
        self.t.set_focus("code", None, self.c.wall)
        for _ in range(3):
            self.c.advance(5)
            self.c.beat(self.t)
        # No stop(): what a crash would leave behind.
        self.assertEqual(rows(self.store), [("code", 0, 15)])

    def test_inputs_after_stop_are_ignored(self):
        self.t.set_focus("code", None, self.c.wall)
        self.c.advance(10)
        self.t.stop(self.c.wall)
        self.t.set_idle(False, self.c.wall)  # e.g. idle watcher cleanup during shutdown
        self.c.advance(5)
        self.c.beat(self.t)
        self.assertEqual(rows(self.store), [("code", 0, 10)])

    def test_flicker_intervals_are_dropped(self):
        self.t.set_focus("code", None, self.c.wall)
        self.c.advance(10)
        self.t.set_focus("firefox", None, self.c.wall)
        self.c.advance(0.1)
        self.t.set_focus("code", None, self.c.wall)
        self.c.advance(10)
        self.t.stop(self.c.wall)
        self.assertEqual([a for a, _, _ in rows(self.store)], ["code", "code"])


class CrashRecoveryTest(unittest.TestCase):
    def test_restart_after_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "db.sqlite")
            c = Clock()
            store = Store(path)
            t = Tracker(store)
            t.set_focus("code", None, c.wall)
            c.advance(5)
            c.beat(t)
            c.advance(3)  # crash 3 s after the last flush; nothing closes the row
            store.db.close()

            c.advance(30)  # systemd restarts us
            store2 = Store(path)
            store2.clamp_future(c.wall)
            t2 = Tracker(store2)
            t2.set_focus("code", None, c.wall)
            c.advance(5)
            t2.stop(c.wall)
            self.assertEqual(rows(store2), [("code", 0, 5), ("code", 38, 43)])

    def test_clamp_future_rows(self):
        store = Store(":memory:")
        store.open_interval("code", T0)
        iid = store.open_interval("code", T0 + 100)
        store.extend_interval(iid, T0 + 200)
        store.clamp_future(T0 + 50)
        self.assertEqual(rows(store), [("code", 0, 0)])


if __name__ == "__main__":
    unittest.main()
