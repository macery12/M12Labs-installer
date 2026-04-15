"""System helpers for the M12Labs panel installer.

Provides command execution, package management, and privilege helpers.
Modelled after installer/build.py but without Node/pnpm-specific logic.

Public API::

    run_command(cmd, cwd=None) -> bool
    run_command_no_cwd(cmd) -> bool
    run_as_www_data(cmd, cwd=None) -> bool
    get_package_manager() -> str | None
    with_privilege(cmd) -> list[str] | None
    install_packages(pkgs) -> bool
    read_env_value(env_path, key) -> str | None
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Sequence

_logger = logging.getLogger("m12labs.setup")


def read_env_value(env_path: Path, key: str) -> str | None:
    """Return the value of *key* from a ``.env`` file, or ``None`` if absent.

    Returns an empty string when the key exists but has no value (``KEY=``).
    Returns ``None`` when the key is not present at all or the file cannot
    be read.

    This shared helper avoids duplicating ``.env`` parsing across modules.
    """
    try:
        text = env_path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(rf"^{re.escape(key)}=(.*)$", text, re.MULTILINE)
    return match.group(1).strip() if match else None


def run_command(cmd: Sequence[str], cwd: Path | None = None) -> bool:
    """Run *cmd* (optionally in *cwd*), logging and printing it first.

    Returns ``True`` when the process exits with code 0, ``False`` otherwise.
    stdin/stdout/stderr are inherited from the parent process so interactive
    artisan commands pass through to the terminal unchanged.
    """
    _logger.debug("Running command: %s (cwd: %s)", " ".join(cmd), cwd)
    print(f"\n$ {' '.join(cmd)}")
    try:
        completed = subprocess.run(list(cmd), cwd=cwd, check=False)
        success = completed.returncode == 0
        if success:
            _logger.debug("Command succeeded: %s", " ".join(cmd))
        else:
            _logger.warning(
                "Command failed (exit %d): %s", completed.returncode, " ".join(cmd)
            )
        return success
    except FileNotFoundError:
        _logger.error("Command not found: %s", cmd[0])
        print(f"Command not found: {cmd[0]}")
        return False


def run_command_no_cwd(cmd: Sequence[str]) -> bool:
    """Run *cmd* without a specific working directory.

    Identical to :func:`run_command` with ``cwd=None`` but kept as a
    distinct function to match the pattern from ``installer/build.py``.
    """
    return run_command(cmd, cwd=None)


def run_as_www_data(cmd: Sequence[str], cwd: Path | None = None) -> bool:
    """Run *cmd* as the ``www-data`` user via ``sudo -u www-data``.

    Falls back to running the command directly when ``sudo`` is unavailable
    or the current user is already ``www-data``.
    """
    try:
        import pwd
        current_user = pwd.getpwuid(os.getuid()).pw_name
    except Exception:
        current_user = ""

    if current_user == "www-data":
        return run_command(cmd, cwd=cwd)

    if shutil.which("sudo"):
        return run_command(["sudo", "-u", "www-data", *cmd], cwd=cwd)

    _logger.warning("sudo not available; running %s as current user", cmd[0])
    print("Warning: sudo not available, running as current user.")
    return run_command(cmd, cwd=cwd)


def get_package_manager() -> str | None:
    """Return the name of the first supported package manager found on PATH."""
    for pm in ("apt-get", "dnf", "yum", "pacman", "zypper", "apk"):
        if shutil.which(pm):
            return pm
    return None


def with_privilege(cmd: Sequence[str]) -> list[str] | None:
    """Prefix *cmd* with ``sudo`` if not already root.

    Returns ``None`` when neither root nor ``sudo`` is available.
    """
    try:
        is_root = os.geteuid() == 0
    except AttributeError:
        is_root = False

    if is_root:
        return list(cmd)
    if shutil.which("sudo"):
        return ["sudo", *cmd]
    return None


def install_packages(packages: Sequence[str]) -> bool:
    """Install *packages* using the detected system package manager.

    Returns ``True`` when all packages were installed successfully.
    """
    package_manager = get_package_manager()
    if not package_manager:
        print("No supported package manager found (apt-get/dnf/yum/pacman/zypper/apk).")
        return False

    if package_manager == "apt-get":
        update_cmd = with_privilege(["apt-get", "update"])
        install_cmd = with_privilege(["apt-get", "install", "-y", *packages])
    elif package_manager == "dnf":
        update_cmd = None
        install_cmd = with_privilege(["dnf", "install", "-y", *packages])
    elif package_manager == "yum":
        update_cmd = None
        install_cmd = with_privilege(["yum", "install", "-y", *packages])
    elif package_manager == "pacman":
        update_cmd = with_privilege(["pacman", "-Sy"])
        install_cmd = with_privilege(["pacman", "--noconfirm", "-S", *packages])
    elif package_manager == "zypper":
        update_cmd = None
        install_cmd = with_privilege(["zypper", "--non-interactive", "install", *packages])
    else:  # apk
        update_cmd = None
        install_cmd = with_privilege(["apk", "add", *packages])

    if not install_cmd:
        print("Missing root privileges and `sudo` is unavailable; cannot install packages.")
        return False

    print(f"Installing packages via {package_manager}: {', '.join(packages)}")
    if update_cmd and not run_command_no_cwd(update_cmd):
        return False
    return run_command_no_cwd(install_cmd)
