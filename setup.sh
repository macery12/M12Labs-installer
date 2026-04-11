#!/usr/bin/env bash
# setup.sh – M12Labs panel installer bootstrap
#
# Run from anywhere:
#   bash setup.sh
#   sudo bash setup.sh
#
# Recommended one-liner (interactive – keeps stdin as your terminal):
#   bash <(curl -fsSL https://raw.githubusercontent.com/macery12/M12Labs-installer/main/setup.sh)
#
# Non-interactive / automated (skip the confirmation prompt):
#   curl -fsSL https://raw.githubusercontent.com/macery12/M12Labs-installer/main/setup.sh | sudo bash -s -- -y
#
# Flags:
#   -y / --yes        Skip the confirmation prompt (auto-proceed)
#   --confirmed       Internal flag used by the sudo re-exec path
#
# What this script does:
#   1. Verifies required tools (git, python3) are available.
#   2. Clones the macery12/M12Labs-installer repo (or updates it if already cloned).
#   3. Asks for confirmation before performing any privileged work.
#   4. Re-executes itself with sudo if not already running as root.
#   5. Runs python3 -m setup.main inside the repo directory.

set -euo pipefail

REPO_URL="https://github.com/macery12/M12Labs-installer.git"
REPO_BRANCH="main"
INSTALL_DIR="/opt/m12labs-installer"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

info()  { printf '  \033[1;34m*\033[0m  %s\n' "$*"; }
ok()    { printf '  \033[1;32m✓\033[0m  %s\n' "$*"; }
warn()  { printf '  \033[1;33m!\033[0m  %s\n' "$*" >&2; }
die()   { printf '\n\033[1;31mERROR:\033[0m %s\n\n' "$*" >&2; exit 1; }

have() { command -v "$1" >/dev/null 2>&1; }

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------

printf '\n'
printf '  ╔══════════════════════════════════════════════╗\n'
printf '  ║        M12Labs Panel – Setup Bootstrap       ║\n'
printf '  ╚══════════════════════════════════════════════╝\n'
printf '\n'
info "Repository : $REPO_URL"
info "Installer Directory : $INSTALL_DIR"
printf '\n'

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

have git     || die "git is required but not found.  Install git and re-run."
have python3 || die "python3 is required but not found.  Install Python 3.10+ and re-run."

# ---------------------------------------------------------------------------
# Parse flags   (-y/--yes skips the prompt; --confirmed is for internal re-exec)
# ---------------------------------------------------------------------------

_CONFIRMED=0
_YES=0
for _arg in "$@"; do
    case "$_arg" in
        --confirmed) _CONFIRMED=1 ;;
        -y|--yes)    _YES=1; _CONFIRMED=1 ;;
    esac
done

if [ "$_CONFIRMED" -eq 0 ]; then
    printf '  This script will:\n'
    printf '    • Clone or update the M12Labs-installer repository into %s\n' "$INSTALL_DIR"
    printf '    • Install system packages (apt)\n'
    printf '    • Create panel directory\n'
    printf '    • Configure cron and systemd services\n'
    printf '\n'
    printf '  Root / sudo privileges are required for the above steps.\n'
    printf '\n'

    # Prefer /dev/tty so the prompt works even when stdin is a pipe
    # (e.g. curl … | sudo bash).  Fall back gracefully when no TTY exists.
    if [ -c /dev/tty ]; then
        printf '  Proceed? [y/N] ' >/dev/tty
        read -r _confirm </dev/tty
    else
        printf '  No controlling terminal detected.\n'
        printf '  To run non-interactively, pass the -y flag:\n'
        printf '\n'
        printf '    curl -fsSL https://raw.githubusercontent.com/macery12/M12Labs-installer/main/setup.sh | sudo bash -s -- -y\n'
        printf '\n'
        printf 'Aborted.\n\n'
        exit 1
    fi

    case "$_confirm" in
        [yY]|[yY][eE][sS]) ;;
        *) printf '\nAborted.\n\n'; exit 0 ;;
    esac
    printf '\n'
fi

# ---------------------------------------------------------------------------
# Re-exec with sudo if not root
# ---------------------------------------------------------------------------

if [ "$(id -u)" -ne 0 ]; then
    have sudo || die "You are not root and sudo is not available.  Re-run as root."
    # Only re-exec if $0 is a real file on disk (i.e. not a pipe/process-sub).
    if [ -f "$0" ]; then
        info "Re-executing with sudo..."
        exec sudo bash "$0" --confirmed "$@"
    else
        die "Not running as root. Re-run with sudo, e.g.:\n\n  curl -fsSL https://raw.githubusercontent.com/macery12/M12Labs-installer/main/setup.sh | sudo bash -s -- -y"
    fi
fi

# ---------------------------------------------------------------------------
# Clone or update the repository
# ---------------------------------------------------------------------------

if [ -d "$INSTALL_DIR/.git" ]; then
    info "Existing installation found — pulling latest $REPO_BRANCH ..."
    # Warn if the directory has local modifications that will be overwritten.
    if ! git -C "$INSTALL_DIR" diff --quiet HEAD 2>/dev/null; then
        warn "Local modifications detected in $INSTALL_DIR — they will be overwritten."
    fi
    git -C "$INSTALL_DIR" fetch --depth 1 origin "$REPO_BRANCH"
    git -C "$INSTALL_DIR" reset --hard "origin/$REPO_BRANCH"
    ok "Repository updated."
else
    info "Cloning repository into $INSTALL_DIR ..."
    git clone --branch "$REPO_BRANCH" --depth 1 "$REPO_URL" "$INSTALL_DIR"
    ok "Repository cloned."
fi

# ---------------------------------------------------------------------------
# Run the Python installer
# ---------------------------------------------------------------------------

cd "$INSTALL_DIR"
info "Launching M12Labs installer..."
printf '\n'
exec python3 -m setup.main "$@"
