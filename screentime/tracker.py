"""Pure focus-tracking state machine.

The tracker turns a stream of facts (focused app, idle, locked, sleeping,
clock readings) into interval writes on a Store. It does no I/O of its own and
takes every timestamp as an argument, so it can be driven by unit tests.

Time is counted for an app only while all of these hold:
  * a window is focused (layer-shell focus / empty workspace => no app)
  * the user is not idle
  * the session is not locked (logind LockedHint) and is the active session
  * the machine is not going to / coming back from sleep
"""

from dataclasses import dataclass

# A heartbeat gap where CLOCK_BOOTTIME advanced this much more than
# CLOCK_MONOTONIC means the machine was suspended in between.
SLEEP_GAP = 3.0
# Wall clock moved this much differently from CLOCK_BOOTTIME => clock was set.
CLOCK_JUMP = 3.0


@dataclass
class _Open:
    key: tuple[str, str | None]
    interval_id: int
    start: float


@dataclass
class _Beat:
    wall: float
    mono: float
    boot: float


class Tracker:
    def __init__(self, store, track_titles: bool = False):
        self.store = store
        self.track_titles = track_titles
        self.focus: tuple[str, str | None] | None = None
        self.idle = False
        self.locked = False
        self.sleeping = False
        self.current: _Open | None = None
        self._last_beat: _Beat | None = None
        self.stopped = False

    # -- state -------------------------------------------------------------

    @property
    def state(self) -> str:
        if self.sleeping:
            return "sleeping"
        if self.locked:
            return "locked"
        if self.idle:
            return "idle"
        if self.focus is None:
            return "no_focus"
        return "active"

    @property
    def current_app(self) -> str | None:
        return self.current.key[0] if self.current else None

    def _wanted(self) -> tuple[str, str | None] | None:
        if self.focus is None or self.idle or self.locked or self.sleeping:
            return None
        app_id, title = self.focus
        return (app_id, title if self.track_titles else None)

    def _close(self, at: float) -> None:
        if self.current is not None:
            self.store.close_interval(self.current.interval_id, max(at, self.current.start))
            self.current = None

    def _apply(self, now: float) -> None:
        if self.stopped:
            return  # late callbacks during shutdown must not open new intervals
        wanted = self._wanted()
        if self.current is not None and self.current.key == wanted:
            self.store.extend_interval(self.current.interval_id, now)
            return
        self._close(now)
        if wanted is not None:
            interval_id = self.store.open_interval(wanted[0], now, wanted[1])
            self.current = _Open(wanted, interval_id, now)

    # -- inputs ------------------------------------------------------------

    def set_focus(self, app_id: str | None, title: str | None, now: float) -> None:
        self.focus = (app_id, title) if app_id else None
        self._apply(now)

    def set_idle(self, idle: bool, now: float) -> None:
        self.idle = idle
        self._apply(now)

    def set_locked(self, locked: bool, now: float) -> None:
        self.locked = locked
        self._apply(now)

    def set_sleeping(self, sleeping: bool, now: float) -> None:
        self.sleeping = sleeping
        self._apply(now)

    def set_track_titles(self, enabled: bool, now: float) -> None:
        self.track_titles = enabled
        self._apply(now)

    def heartbeat(self, wall: float, mono: float, boot: float) -> None:
        """Flush the open interval and detect suspend gaps / clock jumps.

        `mono` must be CLOCK_MONOTONIC (stops during suspend) and `boot`
        CLOCK_BOOTTIME (keeps running during suspend).
        """
        beat = _Beat(wall, mono, boot)
        last, self._last_beat = self._last_beat, beat
        if last is None:
            self._apply(wall)
            return

        slept = (boot - last.boot) - (mono - last.mono)
        jumped = abs((wall - last.wall) - (boot - last.boot)) > CLOCK_JUMP
        if slept > SLEEP_GAP or jumped:
            # The interval must not span the gap: end it at the last moment we
            # know the machine was awake with a sane clock, start fresh now.
            # An interval opened after the last beat (e.g. on logind's resume
            # signal) already lies on the right side of the gap.
            if self.current is not None and self.current.start <= last.wall:
                self._close(last.wall)
            if wall < last.wall:
                self.store.clamp_future(wall)
            if slept > SLEEP_GAP:
                # We are evidently awake again even if logind's
                # PrepareForSleep(false) got lost.
                self.sleeping = False
        self._apply(wall)

    def stop(self, now: float) -> None:
        self._close(now)
        self.stopped = True
