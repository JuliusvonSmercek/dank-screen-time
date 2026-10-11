"""Idle, lock and sleep signals.

Idle: swayidle over ext-idle-notify-v1. Idle notifications respect idle
inhibitors, so a video player that inhibits idle keeps time counting.

Lock / sleep: logind on the system bus, read with `gdbus` (part of
libglib2.0-bin) so the daemon needs no Python D-Bus bindings.
  * org.freedesktop.login1.Manager.PrepareForSleep(bool)  suspend / hibernate
  * Session.LockedHint  set by DMS's lock screen (and most other lockers)
  * Session.Active      false while another session / VT is in front
"""

import asyncio
import logging
import re
import shutil

log = logging.getLogger(__name__)

LOGIN1 = "org.freedesktop.login1"


async def _sleep_or_stop(stop: asyncio.Event, seconds: float) -> None:
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass


async def _terminate(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is None:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=2)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()


# -- idle ------------------------------------------------------------------


async def watch_idle(get_timeout, on_idle, stop: asyncio.Event, restart: asyncio.Event) -> None:
    """Run swayidle and report idle/active transitions.

    get_timeout() returns the current idle timeout in seconds (0 = disabled).
    Setting `restart` makes the watcher pick up a changed timeout.
    """
    warned = False
    backoff = 1.0
    while not stop.is_set():
        restart.clear()
        timeout = get_timeout()
        binary = shutil.which("swayidle")
        if timeout <= 0 or binary is None:
            if binary is None and not warned:
                log.warning("swayidle not found: idle time will be counted as active")
                warned = True
            on_idle(False)
            await _wait_any(stop, restart, 60)
            continue
        warned = False
        cmd = [binary, "timeout", str(timeout), "echo idle", "resume", "echo active"]
        log.info("starting %s", " ".join(cmd))
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
        )
        started = asyncio.get_running_loop().time()
        try:
            reader = asyncio.ensure_future(_read_idle_lines(proc, on_idle))
            waiter_stop = asyncio.ensure_future(stop.wait())
            waiter_restart = asyncio.ensure_future(restart.wait())
            await asyncio.wait(
                {reader, waiter_stop, waiter_restart}, return_when=asyncio.FIRST_COMPLETED
            )
            for task in (reader, waiter_stop, waiter_restart):
                task.cancel()
        finally:
            await _terminate(proc)
            on_idle(False)
        if stop.is_set() or restart.is_set():
            continue
        # swayidle exits when the compositor goes away; retry with backoff.
        ran = asyncio.get_running_loop().time() - started
        backoff = 1.0 if ran > 30 else min(backoff * 2, 30.0)
        log.warning("swayidle exited (code %s), restarting in %.0fs", proc.returncode, backoff)
        await _sleep_or_stop(stop, backoff)


async def _read_idle_lines(proc, on_idle) -> None:
    while True:
        line = await proc.stdout.readline()
        if not line:
            return
        word = line.decode(errors="replace").strip()
        if word == "idle":
            on_idle(True)
        elif word == "active":
            on_idle(False)


async def _wait_any(stop: asyncio.Event, other: asyncio.Event, timeout: float) -> None:
    tasks = {asyncio.ensure_future(stop.wait()), asyncio.ensure_future(other.wait())}
    await asyncio.wait(tasks, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
    for task in tasks:
        task.cancel()


# -- logind ----------------------------------------------------------------

_SESSION_PATH_RE = re.compile(r"objectpath '([^']+)'")
_BOOL_PROP_RE = {
    name: re.compile(rf"'{name}': <(true|false)>") for name in ("LockedHint", "Active")
}
_SLEEP_RE = re.compile(r"PrepareForSleep \((true|false),\)")


def parse_monitor_line(line: str, session_path: str) -> dict:
    """Extract the facts we care about from one `gdbus monitor` line."""
    facts = {}
    match = _SLEEP_RE.search(line)
    if match and line.startswith("/org/freedesktop/login1:"):
        facts["sleeping"] = match.group(1) == "true"
        return facts
    if line.startswith(session_path + ":") and "PropertiesChanged" in line:
        for name, regex in _BOOL_PROP_RE.items():
            m = regex.search(line)
            if m:
                facts[name] = m.group(1) == "true"
    return facts


async def _gdbus(*args: str) -> str | None:
    proc = await asyncio.create_subprocess_exec(
        "gdbus", *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
    except asyncio.TimeoutError:
        await _terminate(proc)
        return None
    return out.decode(errors="replace") if proc.returncode == 0 else None


async def find_session_path() -> str | None:
    """Object path of this user's graphical session (logind User.Display)."""
    out = await _gdbus(
        "call", "--system", "--dest", LOGIN1,
        "--object-path", "/org/freedesktop/login1/user/self",
        "--method", "org.freedesktop.DBus.Properties.Get",
        "org.freedesktop.login1.User", "Display",
    )
    match = _SESSION_PATH_RE.search(out or "")
    if not match or match.group(1) == "/":
        return None
    return match.group(1)


async def read_session_flags(session_path: str) -> dict:
    out = await _gdbus(
        "call", "--system", "--dest", LOGIN1, "--object-path", session_path,
        "--method", "org.freedesktop.DBus.Properties.GetAll", "org.freedesktop.login1.Session",
    )
    flags = {}
    for name, regex in _BOOL_PROP_RE.items():
        m = regex.search(out or "")
        if m:
            flags[name] = m.group(1) == "true"
    return flags


def _locked_from(flags: dict, previous: bool) -> bool:
    if "LockedHint" not in flags and "Active" not in flags:
        return previous
    return flags.get("LockedHint", False) or not flags.get("Active", True)


async def watch_logind(on_locked, on_sleep, stop: asyncio.Event, resync_every: float = 60) -> None:
    """Follow logind lock/active/sleep state, resyncing periodically.

    The periodic GetAll guards against a lost signal leaving us stuck in
    "locked" (which would silently stop all tracking).
    """
    if shutil.which("gdbus") is None:
        log.warning("gdbus not found: lock and suspend detection disabled (heartbeat gap detection still works)")
        return
    backoff = 1.0
    while not stop.is_set():
        session_path = await find_session_path()
        if session_path is None:
            log.warning("could not determine logind session; retrying")
            await _sleep_or_stop(stop, min(backoff, 30))
            backoff *= 2
            continue
        flags = {"LockedHint": False, "Active": True}
        flags.update(await read_session_flags(session_path))
        on_locked(_locked_from(flags, False))

        proc = await asyncio.create_subprocess_exec(
            "gdbus", "monitor", "--system", "--dest", LOGIN1,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        log.info("watching logind session %s", session_path)
        started = asyncio.get_running_loop().time()
        try:
            loop = asyncio.get_running_loop()
            next_resync = loop.time() + resync_every
            while not stop.is_set():
                remaining = max(0.1, next_resync - loop.time())
                try:
                    line = await asyncio.wait_for(proc.stdout.readline(), timeout=remaining)
                except asyncio.TimeoutError:
                    flags.update(await read_session_flags(session_path))
                    on_locked(_locked_from(flags, False))
                    next_resync = loop.time() + resync_every
                    continue
                if not line:
                    break
                facts = parse_monitor_line(line.decode(errors="replace").strip(), session_path)
                if "sleeping" in facts:
                    on_sleep(facts["sleeping"])
                if "LockedHint" in facts or "Active" in facts:
                    flags.update({k: v for k, v in facts.items() if k != "sleeping"})
                    on_locked(_locked_from(flags, False))
        finally:
            await _terminate(proc)
        if stop.is_set():
            return
        ran = asyncio.get_running_loop().time() - started
        backoff = 1.0 if ran > 30 else min(backoff * 2, 30.0)
        log.warning("gdbus monitor exited, restarting in %.0fs", backoff)
        await _sleep_or_stop(stop, backoff)
