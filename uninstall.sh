#!/bin/sh
# uninstall.sh — Remove the M12 Labs extension launcher.
#
# Usage:
#   sh uninstall.sh            # removes the command wrapper only
#   sh uninstall.sh --purge    # also removes the cloned repository directory
#
# Pass --purge to additionally delete the local repository clone.
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
# Parse arguments
# ---------------------------------------------------------------------------

PURGE=0
for arg in "$@"; do
    case "$arg" in
        --purge) PURGE=1 ;;
        *)
            printf 'Unknown option: %s\n' "$arg" >&2
            printf 'Usage: sh uninstall.sh [--purge]\n' >&2
            exit 1
            ;;
    esac
done

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
# Optionally remove the repository clone
# ---------------------------------------------------------------------------

if [ "$PURGE" -eq 1 ]; then
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
else
    log "Repository kept at: $INSTALL_DIR"
    log "(Re-run with --purge to also remove the repository.)"
fi

printf '\nUninstall complete.\n\n'
