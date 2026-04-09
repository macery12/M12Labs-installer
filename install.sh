#!/bin/sh
# install.sh — Install or update the M12 Labs extension launcher.
#
# Usage:
#   sh install.sh
#   curl -fsSL https://raw.githubusercontent.com/macery12/M12Labs-Extensions/main/install.sh | sh
#
# Rerunning this script updates an existing installation.
# Requires: git, python3

set -eu

REPO_URL="https://github.com/macery12/M12Labs-Extensions.git"
REPO_BRANCH="main"
COMMAND_NAME="m12extensions"

# Honour XDG base-dir spec; fall back to ~/.local/{share,bin}.
INSTALL_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/$COMMAND_NAME"
BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
COMMAND_PATH="$BIN_DIR/$COMMAND_NAME"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

log() {
    printf '  %s\n' "$*"
}

die() {
    printf 'Error: %s\n' "$*" >&2
    exit 1
}

have() {
    command -v "$1" >/dev/null 2>&1
}

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

printf '\nM12 Labs Extension Launcher — Installer\n'
printf '========================================\n\n'

have git    || die "git is required but not found. Please install git and try again."
have python3 || die "python3 is required but not found. Please install python3 and try again."

# ---------------------------------------------------------------------------
# Clone or update the repository
# ---------------------------------------------------------------------------

mkdir -p "$INSTALL_DIR" "$BIN_DIR"

if [ -d "$INSTALL_DIR/.git" ]; then
    log "Existing installation found — updating to latest $REPO_BRANCH..."
    # Fetch and hard-reset so local edits don't block the update.
    git -C "$INSTALL_DIR" fetch --depth 1 origin "$REPO_BRANCH"
    git -C "$INSTALL_DIR" reset --hard "origin/$REPO_BRANCH"
    log "Repository updated."
else
    log "Cloning repository into $INSTALL_DIR ..."
    # --depth 1 gives a shallow clone for a faster download.
    git clone --branch "$REPO_BRANCH" --depth 1 "$REPO_URL" "$INSTALL_DIR"
    log "Repository cloned."
fi

# ---------------------------------------------------------------------------
# Write the command wrapper
# ---------------------------------------------------------------------------

# Running  python3 /path/to/launcher/main.py  works because Python adds the
# script's parent directory (launcher/) to sys.path automatically, which lets
# the launcher's internal "from build import …" style imports resolve.
cat > "$COMMAND_PATH" <<EOF
#!/bin/sh
exec python3 "$INSTALL_DIR/launcher/main.py" "\$@"
EOF

chmod +x "$COMMAND_PATH"

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------

printf '\n'
log "Installed command : $COMMAND_PATH"
log "Repository        : $INSTALL_DIR"

# Warn when BIN_DIR is not in PATH (common on fresh setups).
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *)
        printf '\nWarning: %s is not in your PATH.\n' "$BIN_DIR"
        printf 'Add the following line to your shell profile (~/.bashrc, ~/.profile, etc.):\n'
        printf '  export PATH="%s:$PATH"\n' "$BIN_DIR"
        printf 'Then open a new terminal or run:  source ~/.bashrc\n'
        ;;
esac

printf '\nInstallation complete.  Run:\n'
printf '  %s\n\n' "$COMMAND_NAME"
