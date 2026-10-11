#!/usr/bin/env bash
# Remove the Screen Time daemon, CLI, unit and DMS plugin.
#
#   ./uninstall.sh          keep your data and config
#   ./uninstall.sh --purge  also delete ~/.local/share/screentime and ~/.config/screentime
set -euo pipefail

PURGE=0
[ "${1:-}" = "--purge" ] && PURGE=1

UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
PLUGIN_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/DankMaterialShell/plugins/screenTime"

systemctl --user disable --now screentime.service 2>/dev/null || true
rm -f "$UNIT_DIR/screentime.service"
systemctl --user daemon-reload
rm -rf "$HOME/.local/lib/screentime"
rm -f "$HOME/.local/bin/screentime"

if [ -e "$PLUGIN_DIR" ] || [ -L "$PLUGIN_DIR" ]; then
    command -v dms >/dev/null && dms ipc call plugins disable screenTime >/dev/null 2>&1 || true
    rm -rf "$PLUGIN_DIR"
fi

if [ "$PURGE" = 1 ]; then
    rm -rf "${XDG_DATA_HOME:-$HOME/.local/share}/screentime" "${XDG_CONFIG_HOME:-$HOME/.config}/screentime"
    echo "removed screen time, including data and config"
else
    echo "removed screen time; data kept in ${XDG_DATA_HOME:-$HOME/.local/share}/screentime"
fi
