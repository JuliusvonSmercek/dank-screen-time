# Dank Screen Time

A native Screen Time for Linux: a small daemon that records which app has
focus on [niri](https://github.com/YaLTeR/niri), and a
[DankMaterialShell](https://github.com/AvengeMedia/DankMaterialShell) plugin
that shows it as a bar pill, a Material 3 popout and desktop widgets.

- **Accurate:** focus comes from niri's IPC; app_ids are resolved through
  `.desktop` files (Snap and Flatpak included), so nothing shows as "unknown".
- **Only real use counts:** no time for empty workspaces, the launcher, idle,
  a locked screen or suspend. Video players that keep the screen awake still count.
- **Local and tiny:** Python standard library, SQLite, no web UI, no network.

**Why:** I used [ActivityWatch](https://activitywatch.net/) before, but it had
no native UI, no niri/DMS integration, often missed time and labelled many
apps "unknown".

## Install

Requires niri, DMS ≥ 1.6, `/usr/bin/python3` ≥ 3.11, `swayidle` (idle
detection: `sudo apt install swayidle`) and `gdbus` (lock/suspend, preinstalled
on Ubuntu).

```sh
git clone https://github.com/JuliusvonSmercek/dank-screen-time.git && cd dank-screen-time
./install.sh            # --dev symlinks instead of copying
```

This installs the CLI to `~/.local/bin/screentime`, starts the
`screentime.service` user unit, writes a default config, generates the
category mapping from your installed apps, and installs the plugin. Then:

1. Enable **Screen Time** in DMS Settings → Plugins and add it to your bar.
2. Optional: add **Screen Time** desktop widgets. Each one shows **Today** or
   **This week**; a left click opens the popout in that view.
3. Optional keybind (niri): `Mod+Shift+T { spawn "dms" "ipc" "call" "screenTime" "toggle"; }`

`./uninstall.sh` removes everything except your data (`--purge` removes that too).

## CLI

```sh
screentime status                        # running? counting what?
screentime summary [--range day|week|month] [--date YYYY-MM-DD] [--app ID] [--json]
screentime apps [--unresolved]           # app_ids seen and how they resolve
screentime log --limit 20                # raw intervals
screentime config get | set KEY VALUE
screentime categories generate           # add newly installed apps
```

## Configuration

`~/.config/screentime/config.toml` is reloaded automatically. Most keys can
also be set in the plugin settings.

| key | default | meaning |
| --- | --- | --- |
| `idle_timeout` | `300` | seconds without input before time stops; `0` = off |
| `track_titles` | `false` | also record window titles (shown per app in the popout) |
| `title_retention_days` | `30` | delete older titles, keep the time; `0` = forever |
| `day_start_hour` | `0` | hour a new day starts (`4` = late nights count to the day before) |
| `heartbeat_seconds` | `5` | flush interval; the most a crash can lose |
| `mcp_enabled` | `false` | allow AI assistants to read usage (see below) |
| `mcp_allow_titles` | `false` | also allow them to read window titles |
| `mcp_max_days` | `90` | how far back they may query |

**Categories** live in `~/.config/screentime/categories.toml` as
`"app_id or desktop id" = "Category"` lines. Names are free text, and unlisted
apps appear under their own name. **Window titles** are cleaned before grouping
(no "— Mozilla Firefox", no unread counters), and private-browsing windows are
stored only as "Private window".

## AI assistants (MCP)

`screentime mcp` is a read-only MCP server over **stdio**: the client starts
it as a subprocess, so no port is opened and no password is needed. Turn on
"Allow AI assistants to read screen time" in the plugin settings, then register it:

- **Claude Code:** `claude mcp add --scope user screentime -- ~/.local/bin/screentime mcp`
  (without `--scope user` it only works in the current directory).
- **Claude Desktop:** add this to `~/.config/Claude/claude_desktop_config.json`,
  then restart the app:
  `"mcpServers": {"screentime": {"command": "/home/<you>/.local/bin/screentime", "args": ["mcp"]}}`

Tools: `get_summary`, `get_app_usage`, `list_apps`, and `get_window_titles`
(needs `mcp_allow_titles`). Check with `claude mcp list` or `/mcp`. Every call
is logged to `~/.local/share/screentime/mcp.log`. Remember that whatever
the tools return is sent to the assistant's provider.

## How it works

niri's event stream (`WindowFocusChanged`, `WindowsChanged`, …), swayidle
(`ext-idle-notify`, respects idle inhibitors) and logind (`LockedHint`,
`Active`, `PrepareForSleep`) feed a small state machine. It writes intervals
`(app_id, start, end[, title])` to `~/.local/share/screentime/screentime.db`.

- A heartbeat pushes the open interval's end forward every 5 s, so a crash
  loses at most 5 s.
- Comparing `CLOCK_BOOTTIME` with `CLOCK_MONOTONIC` catches suspends even if
  a logind signal is lost.
- If niri restarts, the daemon finds its new socket and reconnects.
- Intervals are split by local day and hour only when queried, so midnight
  and DST come out right.

**Security:** nothing listens on the network. Data files are readable by you
only. App ids and titles (which apps and websites choose) are handled as
untrusted text: bound SQL parameters, plain-text rendering, escaped TOML,
cleaned MCP output. Programs running as your user can still read the database.

## Debugging

```sh
journalctl --user -u screentime -f             # focus/idle/lock/sleep transitions
screentime apps --unresolved                   # odd names? add StartupWMClass or a category line
journalctl --user -u dms -f | grep -i screen   # plugin errors
python3 -m unittest discover -s tests -t .     # test suite
```

After editing a plugin helper (`St*.qml`), restart DMS
(`systemctl --user restart dms`); `dms ipc call plugins reload screenTime` only
reloads top-level files.

## Contributing, disclaimer, license

Ideas and improvements are welcome as an [issue](https://github.com/JuliusvonSmercek/dank-screen-time/issues) or a
[pull request](https://github.com/JuliusvonSmercek/dank-screen-time/pulls).

All code was generated by Claude (Anthropic, Claude Opus 5.5). I reviewed it
and use it daily, but it comes **without any guarantees**.

[MIT](LICENSE): free to use, modify and share, including commercially; no warranty.
