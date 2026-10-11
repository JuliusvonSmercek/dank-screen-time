"""The tracker daemon: wires niri, idle and logind inputs into the Tracker."""

import asyncio
import json
import logging
import os
import signal
import time

from . import config as config_mod
from . import niri, paths, session, titles
from .store import Store
from .tracker import Tracker

log = logging.getLogger("screentime")


def clocks() -> tuple[float, float, float]:
    return (
        time.time(),
        time.clock_gettime(time.CLOCK_MONOTONIC),
        time.clock_gettime(time.CLOCK_BOOTTIME),
    )


def _exe_of(pid) -> str | None:
    if not isinstance(pid, int) or pid <= 0:
        return None
    try:
        return os.readlink(f"/proc/{pid}/exe")
    except OSError:
        return None


class Daemon:
    def __init__(self):
        self.cfg_path = paths.config_file()
        self.cfg = config_mod.load(self.cfg_path)
        self.cfg_mtime = self._mtime()
        self.store = Store(paths.db_file())
        self.store.clamp_future(time.time())
        self.tracker = Tracker(self.store, track_titles=self.cfg.track_titles)
        self.stop = asyncio.Event()
        self.idle_restart = asyncio.Event()
        self.niri_connected = False
        self._noted_app: str | None = None
        self._next_purge = 0.0

    def _mtime(self) -> float | None:
        try:
            return self.cfg_path.stat().st_mtime
        except OSError:
            return None

    # -- input callbacks -----------------------------------------------------

    def on_focus(self, win: dict | None) -> None:
        now = time.time()
        self.niri_connected = True
        if win is None or not win.get("app_id"):
            self.tracker.set_focus(None, None, now)
            return
        app_id = win["app_id"]
        if app_id != self._noted_app:
            self.store.note_app(app_id, _exe_of(win.get("pid")), now)
            self._noted_app = app_id
        self.tracker.set_focus(app_id, titles.redact(win.get("title")), now)
        log.debug("focus %s", app_id)

    def on_niri_lost(self) -> None:
        self.niri_connected = False
        self.tracker.set_focus(None, None, time.time())

    def on_idle(self, idle: bool) -> None:
        if idle != self.tracker.idle:
            log.info("idle" if idle else "active")
        self.tracker.set_idle(idle, time.time())

    def on_locked(self, locked: bool) -> None:
        if locked != self.tracker.locked:
            log.info("locked" if locked else "unlocked")
        self.tracker.set_locked(locked, time.time())

    def on_sleep(self, sleeping: bool) -> None:
        log.info("preparing for sleep" if sleeping else "resumed")
        self.tracker.set_sleeping(sleeping, time.time())

    # -- periodic work -------------------------------------------------------

    def reload_config(self) -> None:
        mtime = self._mtime()
        if mtime == self.cfg_mtime:
            return
        self.cfg_mtime = mtime
        new = config_mod.load(self.cfg_path)
        log.info("config reloaded: %s", new)
        if new.idle_timeout != self.cfg.idle_timeout:
            self.idle_restart.set()
        if new.track_titles != self.cfg.track_titles:
            self.tracker.set_track_titles(new.track_titles, time.time())
        if new.title_retention_days != self.cfg.title_retention_days:
            self._next_purge = 0.0
        self.cfg = new

    def purge_titles(self, now: float) -> None:
        if now < self._next_purge:
            return
        self._next_purge = now + 3600
        days = self.cfg.title_retention_days
        if days > 0:
            n = self.store.purge_titles(now - days * 86400)
            if n:
                log.info("forgot %d window titles older than %d days", n, days)

    def write_status(self, now: float) -> None:
        cur = self.tracker.current
        status = {
            "pid": os.getpid(),
            "updated_at": now,
            "heartbeat_seconds": self.cfg.heartbeat_seconds,
            "state": self.tracker.state if self.niri_connected else "disconnected",
            "current_app": self.tracker.current_app,
            "current_interval_id": cur.interval_id if cur else None,
            "niri_connected": self.niri_connected,
            "idle_timeout": self.cfg.idle_timeout,
        }
        target = paths.status_file()
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(status))
        os.replace(tmp, target)

    async def heartbeat_loop(self) -> None:
        while not self.stop.is_set():
            wall, mono, boot = clocks()
            self.tracker.heartbeat(wall, mono, boot)
            self.reload_config()
            self.purge_titles(wall)
            try:
                self.write_status(wall)
            except OSError as exc:
                log.warning("cannot write status: %s", exc)
            try:
                await asyncio.wait_for(self.stop.wait(), timeout=self.cfg.heartbeat_seconds)
            except asyncio.TimeoutError:
                pass

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self.stop.set)
        # SIGHUP (systemctl reload): force a config re-read on the next beat.
        loop.add_signal_handler(signal.SIGHUP, lambda: setattr(self, "cfg_mtime", -1.0))
        log.info("screentime daemon starting (db %s)", self.store.path)
        tasks = [
            asyncio.ensure_future(self.heartbeat_loop()),
            asyncio.ensure_future(niri.follow_focus(self.on_focus, self.on_niri_lost, self.stop)),
            asyncio.ensure_future(
                session.watch_idle(lambda: self.cfg.idle_timeout, self.on_idle, self.stop, self.idle_restart)
            ),
            asyncio.ensure_future(session.watch_logind(self.on_locked, self.on_sleep, self.stop)),
        ]
        await self.stop.wait()
        # Cancel the inputs first: their cleanup reports state (e.g. "not idle")
        # that must not reopen an interval after the final close.
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.tracker.stop(time.time())
        try:
            paths.status_file().unlink()
        except OSError:
            pass
        self.store.close()
        log.info("screentime daemon stopped")


def run(verbose: bool = False) -> int:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(Daemon().run())
    return 0
