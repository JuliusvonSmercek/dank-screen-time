# Screen Time for niri + DankMaterialShell

A native "Screen Time" for Linux: a small tracker daemon that records which
app has focus on [niri](https://github.com/YaLTeR/niri), and a
[DankMaterialShell](https://github.com/AvengeMedia/DankMaterialShell) plugin
that shows where your time goes: a bar pill, a Material 3 popout and a desktop
widget.

- **Accurate on niri.** Focus comes straight from niri's IPC event stream, not
  from wlr-foreign-toplevel, and app_ids are resolved through `.desktop`
  files (including Snap and Flatpak), so apps don't show up as "unknown".
- **Only real use is counted.** Time stops when no window is focused (empty
  workspace, launcher, overview), when you're idle, when the session is
  locked, and across suspend/hibernate. Video players that inhibit idle keep
  counting.
- **Local and tiny.** Python standard library, SQLite in
  `~/.local/share/screentime`, no web UI, no network.

## Requirements

- niri, DankMaterialShell ≥ 1.6
- `/usr/bin/python3` ≥ 3.11 (Ubuntu 24.04+ is fine)
- `swayidle` for idle detection: `sudo apt install swayidle`
- `gdbus` for lock/suspend detection (`libglib2.0-bin`, preinstalled on Ubuntu desktops)

## Install

```sh
git clone <this repo> screen-time && cd screen-time
./install.sh
```

The installer, which needs no root:

1. copies the code to `~/.local/lib/screentime` and puts the `screentime` CLI in `~/.local/bin`
2. writes `~/.config/screentime/config.toml` (only if missing)
3. generates `~/.config/screentime/categories.toml` from your installed apps (existing entries are kept)
4. installs and starts the `screentime.service` systemd user unit
5. installs the DMS plugin into `~/.config/DankMaterialShell/plugins/screenTime`

Then enable **Screen Time** in DMS Settings → Plugins and add it to your bar.
The desktop widget is added from the desktop widgets settings.

`./install.sh --dev` symlinks the code and the plugin to the checkout instead
of copying them, which is handy while hacking. `./uninstall.sh` removes
everything but your data; `./uninstall.sh --purge` removes the data too.

## Using the CLI

```sh
screentime status                       # is it running, what is it counting right now
screentime summary                      # today, human-readable
screentime summary --range week         # this week (Mon–Sun)
screentime summary --range day --date 2026-10-01 --json
screentime apps                         # every app_id seen and how it resolved
screentime log --limit 20               # raw intervals, newest last
screentime config set idle_timeout 600
screentime categories generate          # add entries for newly installed apps
```

`summary --json` is the interface the plugin uses. It contains totals, the
comparison against the 7 days before (days without use count as zero), chart
buckets (24 hours for a day, 7 days for a week), per-app totals with the app's
daily history, and per-category totals.

## Configuration

`~/.config/screentime/config.toml` is reloaded automatically:

| key | default | meaning |
| --- | --- | --- |
| `idle_timeout` | `300` | seconds without input before time stops counting; `0` disables |
| `track_titles` | `false` | also store window titles (privacy: off by default) |
| `day_start_hour` | `0` | local hour a new day starts; `4` makes late nights count towards the previous day |
| `heartbeat_seconds` | `5` | how often the open interval is flushed (max data lost on a crash) |

The plugin's settings page writes the first three keys for you, plus a few
display-only options (refresh interval, top-app icon in the bar, desktop
widget opacity).

## Categories

`~/.config/screentime/categories.toml` maps apps to categories:

```toml
[apps]
"code_code" = "Development"        # Visual Studio Code (Snap)
"firefox_firefox" = "Browsing"
"whatsapp" = "Communication"       # desktop id: also matches app_id whatsapp-nativefier-d40211
```

- Keys are either a Wayland app_id (see `screentime apps`) or a desktop file
  id, so one line also covers apps whose app_id has a random suffix.
- Category names are free text: rename them, merge them, invent new ones.
- The installer generates the initial mapping from each app's freedesktop
  `Categories=` (WebBrowser → Browsing, InstantMessaging/Email →
  Communication, AudioVideo → Media, Game → Games, Office → Productivity, …).
- An app that isn't listed is shown under its own name in the category
  breakdown, never as "unknown".

## How tracking works

```
niri IPC event stream ─┐
swayidle (idle/active) ─┼─► Tracker state machine ─► SQLite intervals (app_id, start, end[, title])
logind via gdbus ───────┘          ▲
  LockedHint, Active,              └── heartbeat every 5 s: flush, detect suspend gaps / clock jumps
  PrepareForSleep
```

- **Focus:** `WindowsChanged`, `WindowOpenedOrChanged`, `WindowClosed` and
  `WindowFocusChanged`. `WindowFocusChanged {"id": null}` means a layer-shell
  surface, an empty workspace or the overview, and counts as no app.
- **Idle:** swayidle over `ext-idle-notify-v1`. Idle notifications respect
  idle inhibitors, so a playing video keeps counting. A shell "keep awake"
  toggle does too.
- **Lock:** logind's `LockedHint`, which DMS's lock screen sets. A session
  that isn't the active one (VT switch, other user) counts as locked.
- **Sleep:** logind's `PrepareForSleep`. As a backup, every heartbeat compares
  `CLOCK_BOOTTIME` (runs during suspend) with `CLOCK_MONOTONIC` (doesn't), so
  no interval ever spans a suspend, even if a signal is lost.
- **Crash safety:** each row always has an `end`, which is pushed forward on
  every heartbeat. A crash loses at most one heartbeat, and nothing needs
  repairing on restart.
- **Reconnects:** if niri restarts, the socket path changes (it contains
  niri's PID). The daemon looks for the new socket and reconnects with backoff.
- **Midnight and DST:** intervals are stored in UTC and split along local day
  and hour boundaries at query time, so midnight rollover and 23/25-hour days
  come out right.

## Debugging

```sh
systemctl --user status screentime
journalctl --user -u screentime -f              # focus/idle/lock/sleep transitions
screentime status                               # stopped / active / idle / locked / no_focus
screentime apps --unresolved                    # app_ids without a matching .desktop file
niri msg --json event-stream                    # what niri reports
dms ipc call plugins reload screenTime           # reload the plugin's top-level files
journalctl --user -u dms -f | grep -i screen    # plugin QML errors
```

- **An app shows a raw or odd name:** run `screentime apps --unresolved`, then
  either give it a `StartupWMClass=` in its `.desktop` file or add a category
  line for the app_id.
- **Idle never triggers:** check that swayidle is installed (`screentime
  status` mentions it) and that nothing is inhibiting idle.
- **The plugin says the tracker isn't running:** `systemctl --user enable
  --now screentime`.
- **Plugin development:** DMS's plugin reload cache-busts only the top-level
  surface files. After editing a helper component (`St*.qml`), restart the
  shell with `systemctl --user restart dms`.

## Tests

```sh
python3 -m unittest discover -s tests -t .
```

The tests cover the interval logic (focus switches, no-focus, idle, lock,
logind and clock-gap suspend, lost resume signals, clock jumps, crash
recovery), aggregation (midnight rollover, DST, day start hour, week bounds,
7-day averages), niri event handling, logind parsing, app resolution and
category generation.
