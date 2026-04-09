#!/bin/sh
# uninstall.sh — Fully remove the M12 Labs extension launcher.
#
# Usage:
#   sh uninstall.sh
#
# Removes the command wrapper and the cloned repository directory.
# No network access is required; this script only touches local files.

set -eu

COMMAND_NAME="m12extensions"

INSTALL_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/$COMMAND_NAME"
BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
COMMAND_PATH="$BIN_DIR/$COMMAND_NAME"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

log() {
    printf '  %s\n' "$*"
}

# ---------------------------------------------------------------------------
# Remove the command wrapper
# ---------------------------------------------------------------------------

printf '\nM12 Labs Extension Launcher — Uninstaller\n'
printf '==========================================\n\n'

if [ -f "$COMMAND_PATH" ]; then
    rm -f "$COMMAND_PATH"
    log "Removed command: $COMMAND_PATH"
else
    log "Command not found (already removed?): $COMMAND_PATH"
fi

# ---------------------------------------------------------------------------
# Remove the repository clone
# ---------------------------------------------------------------------------

if [ -d "$INSTALL_DIR" ]; then
    # Safety check: only remove the directory if it looks like our repo
    # (i.e. it contains a launcher/main.py).  This avoids accidents if the
    # variable somehow resolves to an unexpected path.
    if [ -f "$INSTALL_DIR/launcher/main.py" ]; then
        rm -rf "$INSTALL_DIR"
        log "Removed repository: $INSTALL_DIR"
    else
        log "Skipping removal of $INSTALL_DIR — does not look like the expected repo."
    fi
else
    log "Repository directory not found (already removed?): $INSTALL_DIR"
fi

printf '\nUninstall complete.\n\n'
