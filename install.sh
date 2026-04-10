#!/bin/sh
# install.sh — Install or update the M12 Labs installer.
#
# Recommended usage (two-step, allows you to review the script before running):
#   curl -fsSL https://raw.githubusercontent.com/macery12/M12Labs-installer/main/install.sh -o install.sh
#   sh install.sh
#
# One-liner (pipe to sh) — only use this if you trust the source:
#   curl -fsSL https://raw.githubusercontent.com/macery12/M12Labs-installer/main/install.sh | sh
#
# Rerunning this script updates an existing installation.
# Requires: git, python3

set -eu

REPO_URL="https://github.com/macery12/M12Labs-installer.git"
REPO_BRANCH="main"
COMMAND_NAME="m12labs-installer"

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

ensure_bin_dir_in_path_now() {
    case ":$PATH:" in
        *":$BIN_DIR:"*) ;;
        *)
            PATH="$BIN_DIR:$PATH"
            export PATH
            ;;
    esac
}

ensure_bin_dir_persisted() {
    # Pick a profile file based on the user's shell; fall back to ~/.profile.
    profile_file=""

    case "${SHELL:-}" in
        */bash) profile_file="$HOME/.bashrc" ;;
        */zsh)  profile_file="$HOME/.zshrc" ;;
        *)      profile_file="$HOME/.profile" ;;
    esac

    # Line we want to ensure exists
    path_line='export PATH="$HOME/.local/bin:$PATH"'

    # If BIN_DIR is not the default, use that instead in the persisted line.
    if [ "$BIN_DIR" != "$HOME/.local/bin" ]; then
        # Escape any " characters in BIN_DIR just in case (unlikely).
        esc_bin_dir=$(printf '%s\n' "$BIN_DIR" | sed 's/"/\\"/g')
        path_line="export PATH=\"$esc_bin_dir:\$PATH\""
    fi

    # Create the file if it doesn't exist.
    if [ ! -f "$profile_file" ]; then
        : > "$profile_file"
    fi

    # Only append if the exact line is not already present.
    if ! grep -Fqx "$path_line" "$profile_file"; then
        printf '\n# Added by M12 Labs Installer\n%s\n' "$path_line" >> "$profile_file"
        log "Updated shell profile: $profile_file"
    fi
}

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

printf '\nM12 Labs Installer\n'
printf '==================\n\n'

have git     || die "git is required but not found. Please install git and try again."
have python3 || die "python3 is required but not found. Please install python3 and try again."

# ---------------------------------------------------------------------------
# Clone or update the repository
# ---------------------------------------------------------------------------

mkdir -p "$INSTALL_DIR" "$BIN_DIR"

if [ -d "$INSTALL_DIR/.git" ]; then
    log "Existing installation found — updating to latest $REPO_BRANCH..."
    # Fetch and hard-reset to origin so the managed install stays in sync.
    # This intentionally discards any local changes inside INSTALL_DIR.
    # Do not edit files inside $INSTALL_DIR directly; they will be overwritten
    # the next time you run this installer.
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

# Running  python3 /path/to/installer/main.py  works because Python adds the
# script's parent directory (installer/) to sys.path automatically, which lets
# the installer's internal "from build import …" style imports resolve.
cat > "$COMMAND_PATH" <<EOF
#!/bin/sh
exec python3 "$INSTALL_DIR/installer/main.py" "\$@"
EOF

chmod +x "$COMMAND_PATH"

# ---------------------------------------------------------------------------
# PATH handling (for curl | sh and for future shells)
# ---------------------------------------------------------------------------

# Make BIN_DIR available in this process (helps some usage patterns).
ensure_bin_dir_in_path_now

# Persist BIN_DIR into a shell startup file so future terminals see it.
ensure_bin_dir_persisted

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------

printf '\n'
log "Installed command : $COMMAND_PATH"
log "Repository        : $INSTALL_DIR"

case ":$PATH:" in
    *":$BIN_DIR:"*)
        # BIN_DIR is in PATH for this process.
        ;;
    *)
        # This should be rare now, but keep a friendly hint just in case.
        printf '\nNote: %s may not be in PATH for your current shell.\n' "$BIN_DIR"
        printf 'A PATH export line has been added to your shell profile, but you may need to:\n'
        printf '  - open a new terminal, or\n'
        printf '  - manually run:  source ~/.bashrc  (or your shell config)\n'
        ;;
esac

printf '\nInstallation complete. You can now run:\n'
printf '  %s\n\n' "$COMMAND_NAME"