"""System helpers for the M12Labs panel installer.

Provides command execution, package management, and privilege helpers.
Modelled after archive/installer/build.py but without Node/pnpm-specific logic.

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

# Session-level flag: set to True after apt-get update has been run once.
# Reset to False (stale) whenever a new repository is added so the next
# install_packages() call will re-fetch the package lists.
_apt_cache_fresh: bool = False


def mark_apt_cache_stale() -> None:
    """Mark the apt package cache as stale.

    Call this after adding a new repository (e.g. a PPA) so that the next
    :func:`install_packages` call will run ``apt-get update`` before
    attempting to install packages from the new repo.
    """
    global _apt_cache_fresh
    _apt_cache_fresh = False


def _all_packages_installed(packages: Sequence[str]) -> bool:
    """Return ``True`` if every package in *packages* is already installed.

    Uses ``dpkg-query -s`` which exits 0 only when every listed package is
    installed and properly configured.  Falls back to ``False`` (assume not
    installed) when ``dpkg-query`` is unavailable so the caller will
    proceed with the normal install path.
    """
    if not shutil.which("dpkg-query"):
        return False
    result = subprocess.run(
        ["dpkg-query", "-s", *packages],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


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

    For ``apt-get``, the package lists are only refreshed (``apt-get update``)
    when necessary:

    * All packages are already installed → skip update *and* install entirely.
    * Some packages are missing AND the cache has not been refreshed yet in
      this process → run ``apt-get update`` once, then install.
    * Some packages are missing AND the cache is already fresh (updated
      earlier in the same run) → skip update, install directly.

    Call :func:`mark_apt_cache_stale` after adding a new repository so that
    the next invocation will refresh the lists before installing.

    Returns ``True`` when all packages were installed successfully.
    """
    global _apt_cache_fresh

    package_manager = get_package_manager()
    if not package_manager:
        print("No supported package manager found (apt-get/dnf/yum/pacman/zypper/apk).")
        return False

    if package_manager == "apt-get":
        # Skip everything when every package is already installed.
        if _all_packages_installed(packages):
            print(f"  Packages already installed: {', '.join(packages)}")
            return True
        # Only refresh package lists when the cache has not been updated yet.
        update_cmd = (
            with_privilege(["apt-get", "update"]) if not _apt_cache_fresh else None
        )
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
    if update_cmd:
        if not run_command_no_cwd(update_cmd):
            return False
        if package_manager == "apt-get":
            _apt_cache_fresh = True
    return run_command_no_cwd(install_cmd)
