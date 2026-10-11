"""niri IPC: event-stream client and focused-window model.

Protocol (niri 25.x/26.x): connect to $NIRI_SOCKET, send the JSON string
"EventStream" followed by a newline, read one reply line ({"Ok":"Handled"}),
then one JSON event object per line. Events used here:

  WindowsChanged        {"windows": [Window, ...]}      full snapshot (sent on connect)
  WindowOpenedOrChanged {"window": Window}
  WindowClosed          {"id": int}
  WindowFocusChanged    {"id": int | null}              null => layer-shell / empty workspace / overview

Window: {"id", "title", "app_id", "pid", "workspace_id", "is_focused", ...}
"""

import asyncio
import glob
import json
import logging
import os

log = logging.getLogger(__name__)


class WindowModel:
    """Tracks open windows and which one has focus."""

    def __init__(self):
        self.windows: dict[int, dict] = {}
        self.focused_id: int | None = None

    def handle(self, event: dict) -> bool:
        """Apply one event. Returns True if it may have changed the focused window."""
        if "WindowsChanged" in event:
            self.windows = {w["id"]: w for w in event["WindowsChanged"]["windows"]}
            focused = [w["id"] for w in self.windows.values() if w.get("is_focused")]
            self.focused_id = focused[0] if focused else None
            return True
        if "WindowOpenedOrChanged" in event:
            win = event["WindowOpenedOrChanged"]["window"]
            self.windows[win["id"]] = win
            if win.get("is_focused"):
                self.focused_id = win["id"]
            return win["id"] == self.focused_id
        if "WindowClosed" in event:
            wid = event["WindowClosed"]["id"]
            self.windows.pop(wid, None)
            if wid == self.focused_id:
                self.focused_id = None
                return True
            return False
        if "WindowFocusChanged" in event:
            self.focused_id = event["WindowFocusChanged"]["id"]
            return True
        return False

    def focused(self) -> dict | None:
        if self.focused_id is None:
            return None
        return self.windows.get(self.focused_id)


def candidate_sockets() -> list[str]:
    """$NIRI_SOCKET first, then any niri socket in the runtime dir (newest first).

    The socket name contains niri's PID, so after a niri restart the path in
    our (systemd-inherited) environment is stale and we have to look around.
    """
    found = []
    env = os.environ.get("NIRI_SOCKET")
    if env:
        found.append(env)
    runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    others = glob.glob(os.path.join(runtime, "niri.*.sock"))
    others.sort(key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0, reverse=True)
    for path in others:
        if path not in found:
            found.append(path)
    return found


async def _connect() -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    errors = []
    for path in candidate_sockets():
        try:
            reader, writer = await asyncio.open_unix_connection(path, limit=16 * 1024 * 1024)
        except OSError as exc:
            errors.append(f"{path}: {exc}")
            continue
        writer.write(b'"EventStream"\n')
        await writer.drain()
        reply = await asyncio.wait_for(reader.readline(), timeout=5)
        if not reply:
            writer.close()
            errors.append(f"{path}: closed before reply")
            continue
        data = json.loads(reply)
        if "Ok" not in data:
            writer.close()
            errors.append(f"{path}: {data}")
            continue
        log.info("connected to niri at %s", path)
        return reader, writer
    raise ConnectionError("; ".join(errors) or "no niri socket found")


async def follow_focus(on_focus, on_disconnect, stop: asyncio.Event) -> None:
    """Stream niri events forever, reconnecting with backoff.

    on_focus(window_dict | None) is called whenever the focused window may
    have changed; on_disconnect() when the stream is lost.
    """
    backoff = 0.5
    while not stop.is_set():
        writer = None
        try:
            reader, writer = await _connect()
            backoff = 0.5
            model = WindowModel()
            last = object()
            while True:
                line = await reader.readline()
                if not line:
                    raise ConnectionError("niri closed the event stream")
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    log.warning("bad niri event line: %r", line[:200])
                    continue
                if model.handle(event):
                    win = model.focused()
                    sig = None if win is None else (win.get("app_id"), win.get("title"), win.get("pid"))
                    if sig != last:
                        last = sig
                        on_focus(win)
        except asyncio.CancelledError:
            raise
        except (OSError, ConnectionError, asyncio.TimeoutError, json.JSONDecodeError) as exc:
            log.warning("niri IPC unavailable: %s (retrying in %.1fs)", exc, backoff)
        finally:
            if writer is not None:
                writer.close()
        on_disconnect()
        try:
            await asyncio.wait_for(stop.wait(), timeout=backoff)
        except asyncio.TimeoutError:
            pass
        backoff = min(backoff * 2, 10.0)

