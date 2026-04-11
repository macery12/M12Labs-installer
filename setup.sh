#!/usr/bin/env bash
# setup.sh – M12Labs panel installer bootstrap
#
# Run from anywhere:
#   bash setup.sh
#   sudo bash setup.sh
#
# This script always runs the Python installer relative to its own location,
# so it works regardless of the current working directory.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 is required. Please install Python 3.10+ and re-run."
    exit 1
fi

cd "$SCRIPT_DIR"
exec python3 setup/main.py "$@"
