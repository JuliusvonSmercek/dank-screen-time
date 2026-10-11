#!/usr/bin/env bash
# Install the Screen Time daemon, CLI, systemd user unit and DMS plugin.
#
#   ./install.sh              copy everything into place
#   ./install.sh --dev        symlink code and plugin to this checkout instead
#   ./install.sh --no-plugin  skip the DankMaterialShell plugin
#
# Nothing here needs root. Config and data in ~/.config/screentime and
# ~/.local/share/screentime are never overwritten.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON=/usr/bin/python3
LIB_DIR="$HOME/.local/lib/screentime"
BIN="$HOME/.local/bin/screentime"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
CONF_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/screentime"
PLUGIN_ID=screenTime
PLUGIN_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/DankMaterialShell/plugins/$PLUGIN_ID"

DEV=0
PLUGIN=1
for arg in "$@"; do
    case "$arg" in
        --dev) DEV=1 ;;
        --no-plugin) PLUGIN=0 ;;
        -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done

info() { printf '\033[1;34m::\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*" >&2; }

# -- dependencies ---------------------------------------------------------------
if ! "$PYTHON" -c 'import sys, sqlite3, tomllib; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
    echo "error: $PYTHON 3.11+ with sqlite3 is required" >&2
    exit 1
fi
command -v gdbus >/dev/null || warn "gdbus not found (apt install libglib2.0-bin): lock/suspend detection disabled"
command -v swayidle >/dev/null || warn "swayidle not found (sudo apt install swayidle): idle time will be counted"
command -v niri >/dev/null || warn "niri not found: nothing will be tracked"

# -- code -----------------------------------------------------------------------
info "installing code to $LIB_DIR"
mkdir -p "$LIB_DIR" "$(dirname "$BIN")"
rm -rf "$LIB_DIR/screentime"
if [ "$DEV" = 1 ]; then
    ln -s "$REPO/screentime" "$LIB_DIR/screentime"
else
    cp -r "$REPO/screentime" "$LIB_DIR/screentime"
    find "$LIB_DIR/screentime" -name __pycache__ -type d -prune -exec rm -rf {} +
fi
cat > "$BIN" <<EOF
#!/bin/sh
# Installed by screen-time/install.sh
PYTHONPATH="$LIB_DIR" exec $PYTHON -s -m screentime "\$@"
EOF
chmod +x "$BIN"

# -- config -----------------------------------------------------------------------
mkdir -p "$CONF_DIR"
if [ ! -e "$CONF_DIR/config.toml" ]; then
    info "writing default $CONF_DIR/config.toml"
    cp "$REPO/config/config.toml" "$CONF_DIR/config.toml"
fi
info "updating category mapping from installed apps"
"$BIN" categories generate

# -- systemd ------------------------------------------------------------------------
info "installing systemd user unit"
mkdir -p "$UNIT_DIR"
cp "$REPO/systemd/screentime.service" "$UNIT_DIR/screentime.service"
systemctl --user daemon-reload
systemctl --user enable screentime.service >/dev/null
systemctl --user restart screentime.service
sleep 1
"$BIN" status || warn "daemon not running yet; see: journalctl --user -u screentime -e"

# -- DMS plugin -----------------------------------------------------------------------
if [ "$PLUGIN" = 1 ]; then
    if [ ! -d "$REPO/plugin/$PLUGIN_ID" ]; then
        warn "plugin sources missing, skipping"
    else
        info "installing DMS plugin to $PLUGIN_DIR"
        mkdir -p "$(dirname "$PLUGIN_DIR")"
        rm -rf "$PLUGIN_DIR"
        if [ "$DEV" = 1 ]; then
            ln -s "$REPO/plugin/$PLUGIN_ID" "$PLUGIN_DIR"
        else
            cp -r "$REPO/plugin/$PLUGIN_ID" "$PLUGIN_DIR"
        fi
        if command -v dms >/dev/null; then
            dms ipc call plugin-scan rescan >/dev/null 2>&1 || true
            dms ipc call plugins reload "$PLUGIN_ID" >/dev/null 2>&1 || true
        fi
        echo "   Enable it in DMS Settings -> Plugins, then add 'Screen Time' to your bar."
    fi
fi

info "done. Try: screentime summary"
